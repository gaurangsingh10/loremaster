"""Snap & Story (vision), Interview the past (in-character, graded) and the Story concierge.

Each call runs through the same guarded runner as episodes (budget check, usage limits, audit, retries) with its own
small budget, and code validates everything the model returns (card ids, shelf ids, safety flags).
"""

from __future__ import annotations

import base64
import re
import time
import uuid
from dataclasses import dataclass, field

from pydantic_ai import BinaryContent, Tool

import instant
from agents import guardian
from agents.common import EpisodeContext, get_agent, run_agent
from agents.researcher import ResearchDeps, tool_read_page, tool_search_wiki
from agents.storyteller import cards_block
from models import ConciergeReply, InterviewAnswer, SnapID
from tokenomics import Ledger
from tools import PACKS, CardRegistry, best_paragraphs, fetch_page_html, sanitize_html, search_wiki

MAX_IMAGE_BYTES = 6_000_000
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _ctx(label: str, budget: float = 0.02) -> EpisodeContext:
    return EpisodeContext(episode_id=label, ledger=Ledger(budget_usd=budget))


# ------------------------------------------------------------------ Snap & Story
GENERIC = {"story", "history", "with", "that", "this", "from", "into", "their", "about", "image", "photo", "style", "design",
           "later", "classical", "rather", "than", "shaped", "generic", "identifiable", "building", "buildings"}


def _plain(text: str | None) -> str | None:
    """Listeners never hear our internal vocabulary: 'the cards available here' -> 'the sources here'."""
    if not text:
        return text
    text = re.sub(r"\b(?:the\s+)?(?:evidence\s+)?cards?\s+(?:available|provided|given)(?:\s+here)?", "the sources here", text, flags=re.I)
    text = re.sub(r"\b(?:evidence\s+)?cards\b", "sources", text, flags=re.I)
    return re.sub(r"\b(?:evidence\s+)?card\b", "source", text, flags=re.I)


def _match_instant(text: str) -> dict | None:
    """Suggest an instant story only on a strong match (names/places in the story's own title or era)."""
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower())} - GENERIC
    best, score = None, 0
    for s in instant.shelf():
        title = f"{s['thread']['title']} {s['thread'].get('era', '')}".lower()
        sc = sum(2 for w in words if w in title) + sum(1 for w in words if w in s["thread"].get("hook", "").lower())
        if sc > score:
            best, score = s, sc
    return best if score >= 4 else None


async def snap(image_b64: str, media_type: str) -> dict:
    if media_type not in IMAGE_TYPES:
        raise ValueError("Please upload a JPEG, PNG, WebP or GIF photo.")
    try:
        data = base64.b64decode(image_b64, validate=True)
    except Exception:
        raise ValueError("That image couldn't be read.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("That photo is over 6 MB. Try a smaller one.")
    ectx = _ctx(f"snap-{uuid.uuid4().hex[:6]}")
    agent = get_agent("identifier", SnapID, layers=ectx.layers, cache=ectx.cache, effort="low")
    ident: SnapID = await run_agent(ectx, "identifier", agent,
                                    ["What is in this photo, and what story should Loremaster tell about it?",
                                     BinaryContent(data=data, media_type=media_type)], label="snap & story")
    out = {"id": ident.model_dump(), "cost_usd": round(ectx.ledger.total_usd, 6), "instant": None, "allowed": ident.safe}
    if ident.safe:
        verdict = guardian.code_check(ident.story_topic)  # same free gate as typed topics
        if verdict:
            out["allowed"], out["id"]["reason"] = False, verdict.reason
        else:
            out["instant"] = _match_instant(f"{ident.what} {ident.story_topic}")
    return out


# ------------------------------------------------------------------ Interview the past
CHARACTERS = [
    {"id": "caesar", "name": "Julius Caesar", "pack": "history", "page": "Julius Caesar", "gender": "male", "era": "Rome, 100–44 BC", "glyph": "🏛", "greeting": "Salve. You wish to question Gaius Julius Caesar? Ask, then. I have crossed rivers for less."},
    {"id": "hypatia", "name": "Hypatia of Alexandria", "pack": "history", "page": "Hypatia", "gender": "female", "era": "Alexandria, c. 360–415", "glyph": "📐", "greeting": "Welcome. I teach mathematics and philosophy here in Alexandria. What would you like to understand?"},
    {"id": "molay", "name": "Jacques de Molay", "pack": "history", "page": "Jacques de Molay", "gender": "male", "era": "Templar Grand Master, d. 1314", "glyph": "✠", "greeting": "I am the last Grand Master of the Temple. Ask what you will; I have little left to lose."},
    {"id": "constantine", "name": "Constantine XI Palaiologos", "pack": "history", "page": "Constantine XI Palaiologos", "gender": "male", "era": "Last Byzantine emperor, d. 1453", "glyph": "☦", "greeting": "The walls still stand, for now. Speak quickly, friend; the Sultan's guns do not rest."},
    {"id": "elizabeth", "name": "Elizabeth I", "pack": "politics", "page": "Elizabeth I", "gender": "female", "era": "England, 1533–1603", "glyph": "👑", "greeting": "You stand before the Queen of England. Choose your questions as carefully as I choose my councillors."},
    {"id": "madison", "name": "James Madison", "pack": "politics", "page": "James Madison", "gender": "male", "era": "USA, 1751–1836", "glyph": "📜", "greeting": "Good day. If men were angels, no government would be necessary. Since they are not, let us talk about how to restrain it."},
    {"id": "newton", "name": "Isaac Newton", "pack": "science", "page": "Isaac Newton", "gender": "male", "era": "England, 1643–1727", "glyph": "🍎", "greeting": "You may ask, though I warn you I dislike being contradicted. And no, you may not ask about the apple first."},
    {"id": "lovelace", "name": "Ada Lovelace", "pack": "technology", "page": "Ada Lovelace", "gender": "female", "era": "England, 1815–1852", "glyph": "⚙", "greeting": "Mr Babbage's Engine can do far more than arithmetic, I'm certain of it. What would you like to know?"},
    {"id": "tesla", "name": "Nikola Tesla", "pack": "technology", "page": "Nikola Tesla", "gender": "male", "era": "1856–1943", "glyph": "⚡", "greeting": "Alternating current is the future. Ask me anything, except to praise Mr Edison."},
    {"id": "bane", "name": "Darth Bane", "pack": "star_wars", "page": "Darth Bane", "gender": "male", "era": "Sith Lord, ~1000 BBY", "glyph": "✷", "greeting": "Two there should be. No more, no less. You may ask your questions, apprentice."},
    {"id": "mothma", "name": "Mon Mothma", "pack": "star_wars", "page": "Mon Mothma", "gender": "female", "era": "Senator & Rebel leader", "glyph": "✦", "greeting": "I served in the Senate long enough to watch it surrender its own freedom. Ask, and I'll tell you how it happened."},
    {"id": "valdor", "name": "Constantin Valdor", "pack": "warhammer40k", "page": "Constantin Valdor", "gender": "male", "era": "Captain-General of the Custodes, M30–M31", "glyph": "☩", "greeting": "I guard the Emperor. Your questions will be answered as far as my oaths allow, and no further."},
]
BY_CHAR = {c["id"]: c for c in CHARACTERS}
NO_ROLEPLAY = re.compile(r"\b(hitler|himmler|goebbels|heydrich|eichmann|stalin|pol pot|mengele|bin laden|mladi[cć]|karad[zž]i[cć])\b", re.I)


@dataclass
class Interview:
    sid: str
    char: dict
    registry: CardRegistry
    ledger: Ledger
    history: list[tuple[str, str]] = field(default_factory=list)
    created: float = field(default_factory=time.time)


INTERVIEWS: dict[str, Interview] = {}


async def start_interview(char_id: str | None, custom_name: str | None) -> dict:
    if char_id and char_id in BY_CHAR:
        ch = dict(BY_CHAR[char_id])
    else:
        name = (custom_name or "").strip()[:80]
        if not name:
            raise ValueError("Pick a character or type a name.")
        if NO_ROLEPLAY.search(name) or guardian.code_check(name):
            raise ValueError("Loremaster won't voice perpetrators of atrocities in character. Try a documentary episode about them instead.")
        pack = "star_wars" if re.search(r"jedi|sith|darth|skywalker|palpatine|leia|vader|yoda", name, re.I) else \
               "warhammer40k" if re.search(r"primarch|custodes|astartes|horus|emperor of mankind|inquisitor|guilliman|lorgar", name, re.I) else "history"
        hits = await search_wiki(pack, name, limit=3)
        if not hits:
            raise ValueError(f"I couldn't find {name} in the sources.")
        ch = {"id": f"custom-{uuid.uuid4().hex[:6]}", "name": hits[0]["title"], "pack": pack, "page": hits[0]["title"],
              "gender": "male", "era": "", "glyph": "✒", "greeting": f"You've summoned {hits[0]['title']}. Ask your questions."}
    page = await fetch_page_html(ch["pack"], ch["page"])
    if not page:
        raise ValueError("The sources for that character are unavailable right now.")
    paras, _ = sanitize_html(page["html"])
    lead = " ".join(paras[:2])
    if ch["id"].startswith("custom-") and ch["pack"] == "history":
        # A fictional character Wikipedia knows (e.g. Ahsoka Tano): switch to the lore wiki for in-universe sources.
        lore = "star_wars" if "Star Wars" in lead[:800] else "warhammer40k" if "Warhammer" in lead[:800] else None
        if lore and (hit := await search_wiki(lore, ch["name"], limit=1)) and (lp := await fetch_page_html(lore, hit[0]["title"])):
            ch.update(pack=lore, page=hit[0]["title"]); page = lp
            paras, _ = sanitize_html(page["html"]); lead = " ".join(paras[:2])
        her, his = len(re.findall(r"\b(she|her)\b", lead, re.I)), len(re.findall(r"\b(he|his|him)\b", lead, re.I))
        ch["gender"] = "female" if her > his else "male"
    if ch["pack"] in ("history", "politics", "science", "technology") and re.search(r"\([^()]*\bborn\b[^()]*\d{4}[^()]*\)", lead[:600]):
        raise ValueError("Loremaster only interviews people from history, not living people.")
    reg = CardRegistry()
    for p in best_paragraphs(paras, f"{ch['name']} life career famous known", 6):
        reg.add(ch["pack"], page["title"], page["url"], p, PACKS[ch["pack"]]["license"])
    sid = uuid.uuid4().hex[:10]
    INTERVIEWS[sid] = Interview(sid=sid, char=ch, registry=reg, ledger=Ledger(budget_usd=0.05))
    return {"sid": sid, "character": ch, "cards": len(reg.cards)}


async def ask_interview(sid: str, question: str) -> dict:
    iv = INTERVIEWS.get(sid)
    if not iv:
        raise KeyError("interview not found")
    if len(iv.history) >= 12:
        raise ValueError("That's twelve questions. Start a new interview to keep going.")
    verdict = guardian.code_check(question)
    if verdict:
        return {"refused": True, "reason": verdict.reason}
    ectx = EpisodeContext(episode_id=f"interview-{sid}", ledger=iv.ledger, registry=iv.registry)
    deps = ResearchDeps(ectx=ectx, allowed_packs=[iv.char["pack"]], new_card_ids=[])
    agent = get_agent("interviewer", InterviewAnswer, layers=ectx.layers, cache=ectx.cache, deps_type=ResearchDeps,
                      with_style=False, tools=[Tool(tool_search_wiki, name="search_wiki"), Tool(tool_read_page, name="read_page")])
    recent = "\n".join(f"Listener: {q}\n{iv.char['name']}: {a}" for q, a in iv.history[-4:])
    prompt = (f"You are {iv.char['name']} ({iv.char.get('era', '')}). Evidence pack: {iv.char['pack']}.\n"
              f"{cards_block(list(iv.registry.cards.values()))}\n\nConversation so far:\n{recent or '(none)'}\n\n"
              f"<listener_question>{question}</listener_question>")
    ans: InterviewAnswer = await run_agent(ectx, "interviewer", agent, prompt, deps=deps, label=f"{iv.char['name']}: {question[:40]}")
    valid = iv.registry.cards
    for c in ans.claims:  # code tripwire
        c.evidence_ids = [e for e in c.evidence_ids if e in valid]
        if not c.evidence_ids and c.grade not in ("Interpretation", "Unsupported"):
            c.grade = "Unsupported"
    iv.history.append((question, ans.in_character))
    return {"answer": ans.in_character, "aside": _plain(ans.aside),
            "claims": [{**c.model_dump(), "evidence": [valid[e].model_dump() for e in c.evidence_ids]} for c in ans.claims],
            "cost_usd": round(iv.ledger.total_usd, 6)}


# ------------------------------------------------------------------ Story concierge
async def concierge(message: str) -> dict:
    verdict = guardian.code_check(message)
    if verdict:
        return {"message": verdict.reason, "picks": [], "live_idea": ""}
    shelf = instant.shelf()
    listing = "\n".join(f"- {s['id']} | {s['thread']['title']} | {s['thread'].get('genre') or s['thread']['mode']} | {s['thread']['hook']}" for s in shelf)
    ectx = _ctx(f"concierge-{uuid.uuid4().hex[:6]}", 0.01)
    agent = get_agent("concierge", ConciergeReply, layers=ectx.layers, cache=ectx.cache, effort="low")
    rep: ConciergeReply = await run_agent(ectx, "concierge", agent,
                                          f"Instant stories:\n{listing}\n\n<listener_message>{message}</listener_message>", label="concierge")
    by_id = {s["id"]: s for s in shelf}
    picks = [{"why": p.why, "story": by_id[p.instant_id]} for p in rep.picks if p.instant_id in by_id][:3]  # only real stories
    return {"message": rep.message, "picks": picks, "live_idea": rep.live_idea.strip()[:200], "cost_usd": round(ectx.ledger.total_usd, 6)}
