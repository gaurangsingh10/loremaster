"""Pre-build the Instant Stories shelf: 10-min stories with chapter 1 AND all three branch continuations, so play and
choose are both instant. Uses the same agents, evidence and grading as live episodes (real gpt-6-luna runs).

    python scripts/build_instant.py                  # build every topic in data/instant/topics.json that's missing
    python scripts/build_instant.py --only rome-imperium --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pipeline  # noqa: E402
from agents import librarian, showrunner  # noqa: E402
from models import ChapterBeat, EpisodeRequest, Thread  # noqa: E402

INSTANT = ROOT / "data" / "instant"


async def build_one(thread: Thread) -> dict:
    req = EpisodeRequest(thread_id=None, topic=thread.title, mode=thread.mode, minutes=10)
    run = pipeline.new_run(req)
    run.episode.thread = thread
    ectx, ep = run.ectx, run.episode
    ectx.ledger.budget_usd = 0.05
    t0 = time.time()
    plan = await showrunner.plan_episode(ectx, thread, 10, 2)
    ep.title, ep.logline, ep.plan = plan.title, plan.logline, plan.chapters
    ch1 = await pipeline.make_chapter(run, plan.chapters[0], None)
    ep.chapters = [ch1]
    summary = pipeline.summary_of(ep)

    async def branch(option: str):
        nb = await showrunner.next_beat(ectx, thread, summary, option, 1)
        beat = ChapterBeat(title=nb.title, focus=nb.focus, queries=nb.queries, packs=nb.packs)
        sub = pipeline.EpisodeRun(episode=ep.model_copy(deep=True), ectx=ectx)
        sub.episode.chapters[-1].chosen_branch = option
        return option, await pipeline.make_chapter(sub, beat, option)

    results = await asyncio.gather(*(branch(o) for o in ch1.branch_options))
    reading = await librarian.recommend(ectx, thread, ep.title, [ch1.title] + [c.title for _, c in results])
    bundle = {"thread": thread.model_dump(), "title": ep.title, "logline": ep.logline,
              "plan": [b.model_dump() for b in plan.chapters], "chapter1": ch1.model_dump(),
              "branches": {o: c.model_dump() for o, c in results}, "reading": [r.model_dump() for r in reading.items],
              "usage": [u.model_dump() for u in ectx.ledger.usage_list()], "build_cost_usd": round(ectx.ledger.total_usd, 6),
              "build_seconds": round(time.time() - t0, 1)}
    return bundle


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--parallel", type=int, default=4)
    a = ap.parse_args()
    topics = [Thread(**t) for t in json.loads((INSTANT / "topics.json").read_text())]
    todo = [t for t in topics if (not a.only or t.id in a.only) and (a.force or not (INSTANT / f"{t.id}.json").exists())]
    sem = asyncio.Semaphore(a.parallel)

    async def go(t: Thread):
        async with sem:
            print(f"building {t.id} …", flush=True)
            try:
                b = await build_one(t)
            except Exception as e:
                print(f"  FAILED {t.id}: {type(e).__name__}: {e}", flush=True)
                return
            (INSTANT / f"{t.id}.json").write_text(json.dumps(b, indent=1, ensure_ascii=False))
            print(f"  done {t.id}: '{b['title']}' ${b['build_cost_usd']:.4f} {b['build_seconds']}s", flush=True)

    await asyncio.gather(*(go(t) for t in todo))
    total = sum(json.loads(p.read_text())["build_cost_usd"] for p in INSTANT.glob("*.json") if p.name != "topics.json")
    print(f"shelf build cost so far: ${total:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
