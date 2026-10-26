"""Showrunner (boss): plans the episode arc, re-plans after each branch choice, and invents "Surprise me" threads.

Design choice: the Showrunner plans and code hands work to the specialists (a fixed pipeline), instead of
letting a boss LLM call specialists in a free loop. Same multi-agent division of labor, but no runaway loops,
predictable cost, and the boss's context never balloons with every chapter's evidence.
"""

from __future__ import annotations

from pydantic import BaseModel

from agents.common import EpisodeContext, get_agent, run_agent
from models import EpisodePlan, NextBeat, Thread


class Menu(BaseModel):
    threads: list[Thread]


def _split_queries(queries: list[str], packs: list[str]) -> list[str]:
    return [q for q in queries if q.strip()][:4]


async def plan_episode(ectx: EpisodeContext, thread: Thread, minutes: int, chapters: int) -> EpisodePlan:
    agent = get_agent("showrunner", EpisodePlan, layers=ectx.layers, cache=ectx.cache)
    prompt = (f"EPISODE PLAN\nThread: {thread.title}\nHook: {thread.hook}\nMode: {thread.mode}\n"
              f"Packs: {thread.packs}\nLength: {minutes} minutes = exactly {chapters} chapters.")
    plan: EpisodePlan = await run_agent(ectx, "showrunner", agent, prompt, label=f"plan: {thread.title}")
    plan.chapters = plan.chapters[:chapters]
    for beat in plan.chapters:
        beat.packs = [p for p in beat.packs if p in thread.packs] or list(thread.packs)
        beat.queries = _split_queries(beat.queries, beat.packs)
    return plan


async def next_beat(ectx: EpisodeContext, thread: Thread, summary: str, branch: str, remaining: int) -> NextBeat:
    agent = get_agent("showrunner", NextBeat, layers=ectx.layers, cache=ectx.cache)
    prompt = (f"NEXT BEAT\nThread: {thread.title} (mode {thread.mode}, packs {thread.packs})\n"
              f"Episode so far:\n{summary}\n\nThe listener chose: <branch>{branch}</branch>\n"
              f"Chapters remaining including this one: {remaining}.")
    beat: NextBeat = await run_agent(ectx, "showrunner", agent, prompt, label=f"next beat: {branch[:40]}")
    beat.packs = [p for p in beat.packs if p in thread.packs] or list(thread.packs)
    beat.queries = _split_queries(beat.queries, beat.packs)
    return beat


async def surprise_menu(ectx: EpisodeContext, mode: str, n: int = 2) -> list[Thread]:
    agent = get_agent("showrunner", Menu, layers=ectx.layers, cache=ectx.cache)
    prompt = (f"MENU\nPropose {n} surprising threads for mode '{mode}'. Available packs: history, science, technology, "
              "politics (all Wikipedia), star_wars, warhammer40k. Crossover threads use one nonfiction pack + exactly one universe.")
    menu: Menu = await run_agent(ectx, "showrunner", agent, prompt, label="surprise me")
    out = []
    for t in menu.threads[:n]:
        t.curated = False
        t.packs = [p for p in t.packs if p in ("history", "science", "technology", "politics", "star_wars", "warhammer40k")] or ["history"]
        out.append(t)
    return out
