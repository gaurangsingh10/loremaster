"""Append-only logs: output/audit_trail.json (every agent step) and output/usage_log.json (every episode).

Never wiped between runs. Each file is a JSON array; we rewrite it with the new record appended, under a lock.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import AUDIT_PATH, USAGE_LOG_PATH
from models import AuditEntry

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, record: dict) -> None:
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(path.read_text()) if path.exists() else []
            if not isinstance(data, list):
                data = []
        except json.JSONDecodeError:
            data = []
        data.append(record)
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def short(value, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def audit(episode_id: str, agent: str, event: str, **kw) -> dict:
    entry = AuditEntry(ts=now(), episode_id=episode_id, agent=agent, event=event,
                       **{k: (short(v) if k in ("args", "result") and v is not None else v) for k, v in kw.items()})
    record = entry.model_dump(exclude_none=True)
    _append(AUDIT_PATH, record)
    return record


def log_usage(record: dict) -> None:
    _append(USAGE_LOG_PATH, {"ts": now(), **record})


def read_audit(episode_id: str | None = None, limit: int = 300) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    data = json.loads(AUDIT_PATH.read_text())
    if episode_id:
        data = [d for d in data if d.get("episode_id") == episode_id]
    return data[-limit:]


def read_usage(limit: int = 200) -> list[dict]:
    return json.loads(USAGE_LOG_PATH.read_text())[-limit:] if USAGE_LOG_PATH.exists() else []
