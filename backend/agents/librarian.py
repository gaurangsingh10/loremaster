"""Librarian: 2-3 further-reading picks from real Open Library results (described, never quoted)."""

from __future__ import annotations

from agents.common import EpisodeContext, get_agent, run_agent
from models import ReadingList, Thread
from tools import search_open_library

QUERIES = {
    "history": ["historical fiction {era}", "{title} history"],
    "science": ["popular science {title}", "{title}"],
    "technology": ["history of technology {title}", "{title}"],
    "politics": ["political history {title}", "{title}"],
    "star_wars": ["Star Wars novel {kw}"],
    "warhammer40k": ["Horus Heresy", "Warhammer 40,000 novel {kw}"],
}


async def recommend(ectx: EpisodeContext, thread: Thread, episode_title: str, chapter_titles: list[str]) -> ReadingList:
    kw = thread.universe or thread.title
    results: list[dict] = []
    for pack in thread.packs:
        for q in QUERIES.get(pack, [])[:2]:
            results += await search_open_library(q.format(era=thread.era or thread.title, title=thread.title, kw=kw), 4)
    if not results:
        return ReadingList(items=[])
    agent = get_agent("librarian", ReadingList, layers=ectx.layers, cache=ectx.cache)
    listing = "\n".join(f"- {r['title']} | {r['author']} | {r['year']} | {r['url']}" for r in results[:14])
    prompt = (f"Episode: {episode_title}\nChapters: {chapter_titles}\nOpen Library results (only use these):\n{listing}")
    reading: ReadingList = await run_agent(ectx, "librarian", agent, prompt, label="further reading")
    known = {r["title"].lower() for r in results}
    reading.items = [i for i in reading.items if i.title.lower() in known][:3]  # never trust invented books
    return reading
