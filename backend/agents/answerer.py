"""Answerer: 'Ask the narrator'. A short spoken answer grounded in the chapter's evidence (or a quick lookup)."""

from __future__ import annotations

from pydantic_ai import Tool

from agents.common import EpisodeContext, get_agent, run_agent
from agents.researcher import ResearchDeps, tool_read_page, tool_search_wiki
from agents.storyteller import cards_block
from config import MAX_TOPIC_CHARS
from models import AnswerDraft, Chapter, Thread
from tools import CardRegistry


def _agent(ectx: EpisodeContext):
    return get_agent("answerer", AnswerDraft, layers=ectx.layers, cache=ectx.cache, deps_type=ResearchDeps, with_style=True,
                     tools=[Tool(tool_search_wiki, name="search_wiki"), Tool(tool_read_page, name="read_page")])


async def answer(parent: EpisodeContext, thread: Thread, ch: Chapter, question: str) -> tuple[AnswerDraft, dict]:
    cards = []
    seen = set()
    for c in ch.claims:
        for e in c.evidence:
            if e.id not in seen:
                seen.add(e.id); cards.append(e)
    # a private registry seeded with the chapter's cards; new lookups get Q-ids so they can't collide
    ectx = EpisodeContext(episode_id=parent.episode_id, ledger=parent.ledger, emit=parent.emit, layers=parent.layers,
                          cache=parent.cache, registry=CardRegistry(prefix="Q", seed=cards))
    deps = ResearchDeps(ectx=ectx, allowed_packs=list(thread.packs), new_card_ids=[])
    prompt = (f"Story: {thread.title} · Chapter {ch.index}: {ch.title}\n"
              f"Chapter so far (for context): {ch.narration[:1500]}…\n\n{cards_block(cards)}\n\n"
              f"<listener_question>{question[:MAX_TOPIC_CHARS]}</listener_question>")
    draft: AnswerDraft = await run_agent(ectx, "answerer", _agent(ectx), prompt, deps=deps, label=f"ask: {question[:50]}")
    valid = ectx.registry.cards
    for c in draft.claims:  # code tripwire, same as chapters: no real card -> Unsupported
        c.evidence_ids = [e for e in c.evidence_ids if e in valid]
        if not c.evidence_ids and c.grade not in ("Interpretation", "Unsupported"):
            c.grade = "Unsupported"
    return draft, valid
