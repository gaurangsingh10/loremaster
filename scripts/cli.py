"""Run one episode headless (auto-picks branch 1 at each break) and print the narration, grades and cost.

    python scripts/cli.py --thread republic-galactic-empire --minutes 10
    python scripts/cli.py --topic "How did the Byzantine Empire survive for 1000 years?" --mode history
    python scripts/cli.py --thread texas-law-medieval-spain --save-sample   # refresh the bundled demo episode
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pipeline  # noqa: E402
from config import EPISODES_DIR  # noqa: E402
from models import EpisodeRequest  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread")
    ap.add_argument("--topic")
    ap.add_argument("--mode", default="crossover", choices=["crossover", "history", "lore"])
    ap.add_argument("--minutes", type=int, default=10, choices=[10, 20, 40])
    ap.add_argument("--skeptic", default="full", choices=["full", "lite", "off"])
    ap.add_argument("--defenses", default="all")
    ap.add_argument("--budget", type=float)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--save-sample", action="store_true", help="save as data/cache/episodes/sample_episode.json")
    a = ap.parse_args()

    req = EpisodeRequest(thread_id=a.thread, topic=a.topic, mode=a.mode, minutes=a.minutes, skeptic=a.skeptic,
                         defenses=a.defenses, budget_usd=a.budget)
    run = pipeline.new_run(req, auto_choose=True)

    async def show(ev: dict) -> None:
        if a.quiet:
            return
        t = ev["type"]
        if t in ("agent_started", "agent_done"):
            extra = f" {ev['seconds']}s ${ev['usage']['cost_usd']:.5f}" if t == "agent_done" else ""
            print(f"  [{ev['agent']}] {t.split('_')[1]} {ev.get('label', '')}{extra}", flush=True)
        elif t == "tool_call":
            print(f"      ↳ {ev['tool']}({ev['args']}) → {ev['result']}", flush=True)
        elif t in ("budget_stop", "refused", "error", "choice"):
            print(f"  ** {t}: {json.dumps({k: v for k, v in ev.items() if k not in ('type', 'ts')})[:300]}", flush=True)

    orig = run.emit

    async def emit(ev: dict) -> None:
        await orig(ev)
        await show(ev)

    run.ectx.emit = emit
    await pipeline.start(run, req)
    ep = run.episode
    print(f"\n=== {ep.title or ep.thread.title} [{ep.status}] {ep.stop_reason}")
    for ch in ep.chapters:
        words = len(ch.narration.split())
        print(f"\n--- Chapter {ch.index}: {ch.title} ({words} words{', revised' if ch.revised else ''})")
        if not a.quiet:
            print(ch.narration)
        for c in ch.claims:
            print(f"   {c.id:>4} {c.grade:<12} {c.text[:110]}")
        print("   branches:", ch.branch_options, "| chosen:", ch.chosen_branch)
    if ep.reading:
        print("\nFurther reading:", [f"{r.title} — {r.author}" for r in ep.reading])
    print("\nUsage by agent:")
    for u in ep.usage:
        print(f"  {u.agent:<12} req={u.requests:<3} in={u.input_tokens:<7} cached={u.cached_tokens:<7} "
              f"write={u.cache_write_tokens:<6} out={u.output_tokens:<6} ${u.cost_usd:.5f}")
    print(f"TOTAL ${ep.total_usd:.5f}   episode id {ep.id}")
    if a.save_sample:
        EPISODES_DIR.mkdir(parents=True, exist_ok=True)
        (EPISODES_DIR / "sample_episode.json").write_text(ep.model_dump_json(indent=1))
        print("saved sample episode for Demo mode")


if __name__ == "__main__":
    asyncio.run(main())
