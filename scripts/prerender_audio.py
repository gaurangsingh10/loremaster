"""Pre-render narration audio for every Instant story (all chapters and branches) with the current voice engine,
so playback is instant. Audio is cached in data/audio/ (content-hashed, gitignored).

    python scripts/prerender_audio.py --voice george
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

import audio  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=audio.DEFAULT_VOICE)
    a = ap.parse_args()
    print("engine:", audio.engine(), flush=True)
    t0 = time.time()
    files = sorted(p for p in (ROOT / "data" / "instant").glob("*.json") if p.name != "topics.json")
    for p in files:
        b = json.loads(p.read_text())
        chapters = [b["chapter1"]] + list(b["branches"].values())
        for ch in chapters:
            await audio.prerender("instant", ch["index"], ch["narration"], a.voice)
        print(f"  {p.stem}: {len(chapters)} chapters ready ({time.time() - t0:.0f}s)", flush=True)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
