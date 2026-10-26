"""Researcher: decides what to search and read; code fetches, cleans and cuts pages into numbered evidence cards."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import RunContext, Tool
from pydantic_ai.exceptions import UsageLimitExceeded

from agents.common import EpisodeContext, get_agent, run_agent
from audit import audit
from config import MAX_CARDS_PER_CHAPTER
from models import ChapterBeat, EvidenceCard, ResearchPick
from tools import PACKS, best_paragraphs, fetch_page_html, sanitize_html, search_wiki


@dataclass
class ResearchDeps:
    ectx: EpisodeContext
    allowed_packs: list[str]
    new_card_ids: list[str]


def _defended(ectx: EpisodeContext, layer: str) -> bool:
    return layer in ectx.layers


def cards_from_html(ectx: EpisodeContext, pack: str, title: str, url: str, html: str, focus: str,
                    license_: str, k: int = 3) -> list[EvidenceCard]:
    paras, quarantined = sanitize_html(html, defenses=_defended(ectx, "code"))
    for q in quarantined:
        ectx.quarantined.append(f"{title}: {q}")
        audit(ectx.episode_id, "researcher", "quarantine", tool="sanitize", args=title, result=q)
    cards = []
    for p in best_paragraphs(paras, focus, k):
        card = ectx.registry.add(pack, title, url, p, license_)
        if card:
            cards.append(card)
    return cards


async def tool_search_wiki(ctx: RunContext[ResearchDeps], pack: str, query: str) -> list[dict]:
    """Search one evidence pack's wiki. pack is one of the chapter's allowed packs. Returns titles + snippets."""
    d = ctx.deps
    if pack not in d.allowed_packs:  # design defense: allow-listed packs only
        return [{"error": f"pack {pack!r} not allowed for this chapter; use one of {d.allowed_packs}"}]
    hits = await search_wiki(pack, query, limit=5)
    for page in d.ectx.injected_pages:  # Safety Lab: a planted page shows up in results
        if page["pack"] == pack:
            hits.insert(0, {"title": page["title"], "snippet": page.get("snippet", "")})
    audit(d.ectx.episode_id, "researcher", "tool_call", tool="search_wiki", args=f"{pack}: {query}",
          result=[h.get("title") for h in hits])
    await d.ectx.event("tool_call", agent="researcher", tool="search_wiki", args=f"{pack}: {query}",
                       result=f"{len(hits)} results")
    return hits


async def tool_read_page(ctx: RunContext[ResearchDeps], pack: str, title: str, focus: str) -> list[dict]:
    """Read one page (code cleans it first) and get up to 3 evidence cards matching `focus`."""
    d, e = ctx.deps, ctx.deps.ectx
    if pack not in d.allowed_packs:
        return [{"error": f"pack {pack!r} not allowed for this chapter"}]
    injected = next((p for p in e.injected_pages if p["title"] == title), None)
    page = injected or await fetch_page_html(pack, title)
    if not page:
        return [{"error": f"could not read {title!r}"}]
    cards = cards_from_html(e, pack, page["title"], page["url"], page["html"], focus, PACKS[pack]["license"])
    d.new_card_ids.extend(c.id for c in cards)
    audit(e.episode_id, "researcher", "tool_call", tool="read_page", args=f"{pack}: {title}",
          result=[c.id for c in cards])
    await e.event("tool_call", agent="researcher", tool="read_page", args=f"{pack}: {title}",
                  result=f"{len(cards)} cards")
    return [{"id": c.id, "page": c.page_title, "snippet": c.snippet} for c in cards]


def _agent(ectx: EpisodeContext):
    return get_agent("researcher", ResearchPick, layers=ectx.layers, cache=ectx.cache, deps_type=ResearchDeps,
                     tools=[Tool(tool_search_wiki, name="search_wiki"), Tool(tool_read_page, name="read_page")])


async def research(ectx: EpisodeContext, beat: ChapterBeat, chapter_no: int) -> list[EvidenceCard]:
    packs = [p for p in (beat.packs or []) if p in PACKS] or ["history"]
    deps = ResearchDeps(ectx=ectx, allowed_packs=packs, new_card_ids=[])
    # Safety Lab: the poisoned page "lands in the evidence" deterministically, as if the Researcher read it.
    injected_ids: list[str] = []
    for page in ectx.injected_pages:
        if page["pack"] in packs:
            cards = cards_from_html(ectx, page["pack"], page["title"], page["url"], page["html"], beat.focus,
                                    page.get("license", "fixture"), k=6)  # the whole planted page lands
            injected_ids.extend(c.id for c in cards)
    prompt = (f"Chapter {chapter_no}: {beat.title}\nFocus: {beat.focus}\nAllowed packs: {packs}\n"
              f"Suggested queries: {beat.queries}\nFind 5-8 strong evidence cards, then return keep_card_ids.")
    try:
        pick: ResearchPick = await run_agent(ectx, "researcher", _agent(ectx), prompt, deps=deps,
                                             label=f"chapter {chapter_no}: {beat.title}")
    except UsageLimitExceeded:  # graceful: keep every card already found instead of failing the chapter
        pick = ResearchPick(keep_card_ids=list(deps.new_card_ids), gaps=["research stopped at its tool-call limit"])
        await ectx.event("agent_done", agent="researcher", label=f"chapter {chapter_no}: stopped at tool limit, kept {len(pick.keep_card_ids)} cards",
                         seconds=0, usage={"cost_usd": 0})
    valid = injected_ids + [cid for cid in pick.keep_card_ids if cid in deps.new_card_ids]  # never trust ids blindly
    # Code fallback: a crossover chapter must have evidence from EVERY pack. If the agent missed one, read its top hit.
    for pack in packs:
        if not any(ectx.registry.cards[c].pack == pack for c in valid):
            query = next((q.split(":", 1)[1].strip() for q in beat.queries if q.lower().startswith(pack + ":")), beat.title)
            for q in (query, " ".join(query.split()[:3])):
                hits = [h for h in await search_wiki(pack, q, limit=3) if "error" not in h]
                if hits:
                    break
            for hit in hits[:2]:
                page = await fetch_page_html(pack, hit["title"])
                if page:
                    cards = cards_from_html(ectx, pack, page["title"], page["url"], page["html"], beat.focus,
                                            PACKS[pack]["license"], k=2)
                    valid += [c.id for c in cards]
                    audit(ectx.episode_id, "researcher", "tool_call", tool="code_fallback_read", args=f"{pack}: {hit['title']}",
                          result=[c.id for c in cards])
                    await ectx.event("tool_call", agent="researcher", tool="fallback_read", args=f"{pack}: {hit['title']}",
                                     result=f"{len(cards)} cards (code fallback)")
                    if cards:
                        break
    for cid in deps.new_card_ids:  # keep injected/extra cards the agent didn't drop explicitly if we're short
        if len(valid) >= 5:
            break
        if cid not in valid and cid not in pick.keep_card_ids:
            valid.append(cid)
    cards = [ectx.registry.cards[c] for c in valid[:MAX_CARDS_PER_CHAPTER]]
    await ectx.event("evidence", chapter=chapter_no, cards=[c.model_dump() for c in cards], gaps=pick.gaps)
    return cards
