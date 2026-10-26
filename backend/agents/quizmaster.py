"""Quizmaster: turns a finished, graded chapter into 'Myth or Fact?' items and one 'Call it' prediction."""

from __future__ import annotations

from agents.common import EpisodeContext, get_agent, run_agent
from agents.storyteller import cards_block
from models import Chapter, ChapterGames, GamesDraft, MythItem


def _chapter_cards(ch: Chapter):
    seen, cards = set(), []
    for c in ch.claims:
        for e in c.evidence:
            if e.id not in seen:
                seen.add(e.id); cards.append(e)
    return cards


async def make_games(ectx: EpisodeContext, ch: Chapter) -> ChapterGames:
    cards = _chapter_cards(ch)
    paras = [p for p in ch.narration.split("\n") if p.strip()]
    numbered = "\n".join(f"P{i}: {p}" for i, p in enumerate(paras))
    claims = "\n".join(f"- [{c.grade}] {c.text} (cards: {[e.id for e in c.evidence]})" for c in ch.claims)
    agent = get_agent("quizmaster", GamesDraft, layers=ectx.layers, cache=ectx.cache)
    draft: GamesDraft = await run_agent(ectx, "quizmaster", agent,
                                        f"Chapter {ch.index}: {ch.title}\n\n{numbered}\n\nGraded claims:\n{claims}\n\n{cards_block(cards)}",
                                        label=f"games for chapter {ch.index}")
    by_id = {c.id: c for c in cards}
    items = []
    for m in draft.myth_or_fact[:3]:  # code validates: only real cards
        items.append(MythItem(**m.model_dump(), evidence=[by_id[e] for e in m.evidence_ids if e in by_id]))
    call = draft.call_it
    if call and (len(call.options) != 3 or not (1 <= call.reveal_para < len(paras)) or not 0 <= call.answer_index <= 2):
        call = None  # malformed prediction: drop it rather than show a broken game
    return ChapterGames(myth_or_fact=items, call_it=call)
