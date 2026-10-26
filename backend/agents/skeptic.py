"""Skeptic: grades every claim against the evidence cards and asks for one rewrite when needed."""

from __future__ import annotations

from agents.common import EpisodeContext, get_agent, run_agent
from agents.storyteller import cards_block
from models import ChapterDraft, ClaimGrades, EvidenceCard
from tools import PACKS


async def grade(ectx: EpisodeContext, draft: ChapterDraft, cards: list[EvidenceCard], precheck: dict[str, str],
                label: str = "") -> ClaimGrades:
    agent = get_agent("skeptic", ClaimGrades, layers=ectx.layers, cache=ectx.cache, effort="low")
    packs = sorted({c.pack for c in cards})
    rules = "\n".join(f"- {p}: {PACKS[p]['grading_rules']}" for p in packs if p in PACKS)
    claims = "\n".join(
        f"{c.id} [{c.kind}] cites {c.evidence_ids or 'nothing'}"
        f"{' (CODE: ' + precheck[c.id] + ')' if c.id in precheck else ''}: {c.text}" for c in draft.claims)
    prompt = (f"Pack grading rules:\n{rules}\n\nClaims to grade:\n{claims}\n\n{cards_block(cards)}\n\n"
              f"Narration as spoken (check that hedged claims are hedged aloud):\n{draft.narration}")
    return await run_agent(ectx, "skeptic", agent, prompt, label=label or f"grade {len(draft.claims)} claims")
