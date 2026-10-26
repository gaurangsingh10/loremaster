"""Pre-build 'Myth or Fact?' + 'Call it' games for every Instant story chapter (stored inside data/instant/*.json).

    python scripts/build_games.py            # only chapters without games
    python scripts/build_games.py --only nero-fiddle --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agents import quizmaster  # noqa: E402
from agents.common import EpisodeContext  # noqa: E402
from models import Chapter  # noqa: E402
from tokenomics import Ledger  # noqa: E402

INSTANT = ROOT / "data" / "instant"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    ledger = Ledger(budget_usd=1.0)
    sem = asyncio.Semaphore(5)
    files = [p for p in sorted(INSTANT.glob("*.json")) if p.name != "topics.json" and (not a.only or p.stem in a.only)]

    async def one(p: Path):
        b = json.loads(p.read_text())
        targets = [("chapter1", b["chapter1"])] + [(k, v) for k, v in b["branches"].items()]
        for key, ch in targets:
            if ch.get("games") and not a.force:
                continue
            async with sem:
                ectx = EpisodeContext(episode_id=f"games-{p.stem}", ledger=ledger)
                try:
                    g = await quizmaster.make_games(ectx, Chapter(**ch))
                    ch["games"] = g.model_dump()
                except Exception as e:
                    print(f"  FAILED {p.stem}/{key[:30]}: {type(e).__name__}: {e}", flush=True)
        p.write_text(json.dumps(b, indent=1, ensure_ascii=False))
        print(f"  {p.stem}: games ready", flush=True)

    await asyncio.gather(*(one(p) for p in files))
    print(f"games build cost: ${ledger.total_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
