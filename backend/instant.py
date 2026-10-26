"""Instant Stories: pre-built 10-min stories (chapter 1 + all three branch continuations) that play with zero wait.

Built offline by scripts/build_instant.py with the same agents and grading as live episodes. Playing one creates a
normal Episode (so it lands in the Lore Library); choosing a branch appends the pre-built chapter instantly.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache

from config import DATA
from models import Chapter, ChapterBeat, Episode, ReadingItem, Thread

INSTANT_DIR = DATA / "instant"


@lru_cache(maxsize=1)
def load_all() -> dict[str, dict]:
    out = {}
    for p in sorted(INSTANT_DIR.glob("*.json")):
        if p.name == "topics.json":
            continue
        try:
            b = json.loads(p.read_text())
            out[p.stem] = b
        except Exception:
            continue
    return out


def shelf() -> list[dict]:
    order = {t["id"]: i for i, t in enumerate(json.loads((INSTANT_DIR / "topics.json").read_text()))} \
        if (INSTANT_DIR / "topics.json").exists() else {}
    items = [{"id": k, "title": b["title"], "logline": b["logline"], "thread": b["thread"],
              "claims": len(b["chapter1"]["claims"]),
              "grades": _grade_mix(b)} for k, b in load_all().items()]
    return sorted(items, key=lambda x: order.get(x["id"], 999))


def _grade_mix(b: dict) -> dict[str, int]:
    mix: dict[str, int] = {}
    for c in b["chapter1"]["claims"]:
        mix[c["grade"]] = mix.get(c["grade"], 0) + 1
    return mix


def new_episode(instant_id: str) -> Episode:
    b = load_all()[instant_id]
    ep = Episode(id=f"i{uuid.uuid4().hex[:9]}", thread=Thread(**b["thread"]), minutes=10, total_chapters=2,
                 title=b["title"], logline=b["logline"], plan=[ChapterBeat(**c) for c in b["plan"]],
                 chapters=[Chapter(**b["chapter1"])], status="waiting_choice")
    return ep


def branch_chapter(instant_id: str, option: str) -> tuple[Chapter, list[ReadingItem]] | None:
    b = load_all().get(instant_id)
    if not b or option not in b["branches"]:
        return None
    return Chapter(**b["branches"][option]), [ReadingItem(**r) for r in b.get("reading", [])]
