"""Listener interaction log (impact evidence): claim taps, branch choices, games, questions, listening time.
Append-only, anonymous (episode id + optional user id), written to output/interaction_log.json."""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, Field

from audit import _append, now
from config import OUTPUT

PATH = OUTPUT / "interaction_log.json"
KINDS = {"claim_open", "branch_choice", "myth_answer", "callit_answer", "ask", "play", "listen_seconds", "reading_click",
         "snap", "interview", "concierge"}


class Interaction(BaseModel):
    kind: str
    episode_id: str = ""
    chapter: int | None = None
    data: dict = Field(default_factory=dict)


def log(i: Interaction, user_id: int | None = None) -> None:
    if i.kind in KINDS:
        _append(PATH, {"ts": now(), "user": user_id, **i.model_dump()})


def summary() -> dict:
    import json
    rows = json.loads(PATH.read_text()) if PATH.exists() else []
    k = Counter(r["kind"] for r in rows)
    myth = [r for r in rows if r["kind"] == "myth_answer"]
    call = [r for r in rows if r["kind"] == "callit_answer"]
    eps = {r["episode_id"] for r in rows if r.get("episode_id")}
    secs = sum(float(r["data"].get("seconds", 0)) for r in rows if r["kind"] == "listen_seconds")
    return {
        "events": len(rows), "episodes": len(eps), "counts": dict(k),
        "claim_taps_per_episode": round(k["claim_open"] / max(len(eps), 1), 2),
        "questions_asked": k["ask"], "interview_questions": k["interview"], "snaps": k["snap"], "concierge_chats": k["concierge"],
        "myth_or_fact_accuracy": round(sum(1 for r in myth if r["data"].get("correct")) / len(myth), 3) if myth else None,
        "callit_accuracy": round(sum(1 for r in call if r["data"].get("correct")) / len(call), 3) if call else None,
        "minutes_listened": round(secs / 60, 1),
    }
