"""Lore Library + tester feedback, in a local SQLite file (stdlib only; created on first run, gitignored)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing

from audit import now
from config import DB_PATH
from models import Episode, Feedback


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS episodes (id TEXT PRIMARY KEY, title TEXT, thread_title TEXT,
                 status TEXT, minutes INT, chapters_done INT, total_chapters INT, total_usd REAL, updated TEXT,
                 json TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, episode_id TEXT,
                 rating INT, minutes_listened INT, listen_tomorrow INT, favorite_moment TEXT, quote TEXT, name TEXT,
                 role TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS blind_tests (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, tester TEXT,
                 json TEXT)""")
    return c


def save_episode(ep: Episode) -> None:
    if ep.demo:
        return
    with closing(_conn()) as c, c:
        c.execute("INSERT OR REPLACE INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (ep.id, ep.title or ep.thread.title, ep.thread.title, ep.status, ep.minutes, len(ep.chapters),
                   ep.total_chapters, ep.total_usd, now(), ep.model_dump_json()))


def load_episode(episode_id: str) -> Episode | None:
    with closing(_conn()) as c:
        row = c.execute("SELECT json FROM episodes WHERE id=?", (episode_id,)).fetchone()
    return Episode.model_validate_json(row[0]) if row else None


def list_episodes(limit: int = 500) -> list[dict]:
    with closing(_conn()) as c:
        rows = c.execute("SELECT id,title,thread_title,status,minutes,chapters_done,total_chapters,total_usd,updated "
                         "FROM episodes ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
    keys = ["id", "title", "thread_title", "status", "minutes", "chapters_done", "total_chapters", "total_usd", "updated"]
    return [dict(zip(keys, r)) for r in rows]


def save_feedback(f: Feedback) -> int:
    with closing(_conn()) as c, c:
        cur = c.execute("INSERT INTO feedback (ts,episode_id,rating,minutes_listened,listen_tomorrow,favorite_moment,"
                        "quote,name,role) VALUES (?,?,?,?,?,?,?,?,?)",
                        (now(), f.episode_id, f.rating, f.minutes_listened,
                         None if f.listen_tomorrow is None else int(f.listen_tomorrow), f.favorite_moment, f.quote,
                         f.name, f.role))
        return cur.lastrowid


def list_feedback() -> list[dict]:
    with closing(_conn()) as c:
        c.row_factory = sqlite3.Row
        return [dict(r) for r in c.execute("SELECT * FROM feedback ORDER BY id")]


def save_blind_test(tester: str, payload: dict) -> int:
    with closing(_conn()) as c, c:
        return c.execute("INSERT INTO blind_tests (ts,tester,json) VALUES (?,?,?)",
                         (now(), tester, json.dumps(payload))).lastrowid
