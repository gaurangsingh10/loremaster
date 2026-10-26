"""Accounts: sign up, log in, sessions and saved listening preferences (local SQLite, stdlib only).

Passwords are never stored: we keep a salted scrypt hash (memory-hard, so offline guessing is slow) and compare in
constant time. Sessions are random 256-bit tokens sent as `Authorization: Bearer …`; only their SHA-256 is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing

from pydantic import BaseModel, Field, field_validator

from config import DB_PATH

SESSION_DAYS = 30
_CHALLENGE_KEY = secrets.token_bytes(32)   # per server run; challenges expire anyway
CHALLENGE_MIN_S, CHALLENGE_MAX_S = 2.0, 3600.0
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


class Prefs(BaseModel):
    voice_gender: str = Field(default="male", pattern="^(male|female)$")
    accent: str = Field(default="uk", pattern="^(uk|us)$")
    tone: str = Field(default="deep", pattern="^(deep|natural)$")
    speed: float = Field(default=1.0, ge=0.7, le=1.6)
    content: str = Field(default="crossover", pattern="^(crossover|history|lore|mix|science|technology|politics)$")
    interests: list[str] | None = None   # several story types; None = older saved settings (use `content`)

    @field_validator("interests")
    @classmethod
    def _topics(cls, v):
        ok = {"crossover", "history", "lore", "science", "technology", "politics"}
        return None if v is None else [t for t in dict.fromkeys(v) if t in ok]
    worlds: list[str] = Field(default_factory=list)      # e.g. ["warhammer40k", "star_wars", "rome", "medieval", "myths"]
    minutes: int = Field(default=20)
    persona: str = ""
    onboarded: bool = False
    # appearance & playback (Settings page)
    theme: str = Field(default="dark", pattern="^(dark|light|system)$")
    text_size: str = Field(default="normal", pattern="^(normal|large|xlarge)$")
    reduce_motion: bool = False
    auto_read: bool = True          # read Ask / Interview answers aloud automatically
    autoplay_next: bool = True      # start the next chapter's audio as soon as it's ready
    usage_stats: bool = True        # anonymous interaction log (curiosity metrics)

    @property
    def voice(self) -> str:
        return f"{self.voice_gender}-{self.accent}-{self.tone}"


class BotCheck(BaseModel):
    challenge: str = ""          # signed timestamp from GET /api/auth/challenge
    human: bool = False          # the "I'm not a robot" checkbox
    website: str = ""            # honeypot: hidden from people, bots tend to fill it


class SignUp(BotCheck):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=200)
    prefs: Prefs | None = None


class PasswordChange(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(min_length=8, max_length=200)


class NameChange(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class Confirm(BaseModel):
    password: str = Field(max_length=200)


class LogIn(BotCheck):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


def new_challenge() -> str:
    ts = f"{time.time():.3f}"
    sig = hmac.new(_CHALLENGE_KEY, ts.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{sig}"


def verify_bot_check(body: BotCheck) -> None:
    """Lightweight bot defence (not a CAPTCHA): human checkbox + honeypot + signed challenge that must be at least
    2 s old (people take longer than that to fill a form; scripts usually don't) and at most an hour old."""
    if body.website.strip():
        raise ValueError("Bot check failed.")
    if not body.human:
        raise ValueError("Please tick “I'm not a robot”.")
    try:
        ts, sig = body.challenge.rsplit(".", 1)
        good = hmac.compare_digest(sig, hmac.new(_CHALLENGE_KEY, ts.encode(), hashlib.sha256).hexdigest()[:32])
        age = time.time() - float(ts)
    except Exception:
        good, age = False, -1
    if not good:
        raise ValueError("The form expired. Please try again.")
    if age < CHALLENGE_MIN_S:
        raise ValueError("That was fast. Please take a second and try again.")
    if age > CHALLENGE_MAX_S:
        raise ValueError("The form expired. Please try again.")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL,
                 name TEXT, pw_salt BLOB NOT NULL, pw_hash BLOB NOT NULL, prefs TEXT, created REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER, expires REAL)""")
    return c


def _hash_pw(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_session(c: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions VALUES (?,?,?)", (_token_hash(token), user_id, time.time() + SESSION_DAYS * 86400))
    return token


def _public(row) -> dict:
    uid, email, name, prefs = row
    return {"id": uid, "email": email, "name": name, "prefs": Prefs(**json.loads(prefs or "{}")).model_dump()}


def sign_up(body: SignUp) -> tuple[str, dict]:
    verify_bot_check(body)
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Please enter a valid email address.")
    _check_strength(body.password)
    salt = secrets.token_bytes(16)
    prefs = (body.prefs or Prefs()).model_dump_json()
    with closing(_conn()) as c, c:
        try:
            cur = c.execute("INSERT INTO users (email,name,pw_salt,pw_hash,prefs,created) VALUES (?,?,?,?,?,?)",
                            (email, body.name.strip(), salt, _hash_pw(body.password, salt), prefs, time.time()))
        except sqlite3.IntegrityError:
            raise ValueError("An account with that email already exists. Try logging in.")
        token = _new_session(c, cur.lastrowid)
        row = c.execute("SELECT id,email,name,prefs FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return token, _public(row)


def log_in(body: LogIn) -> tuple[str, dict]:
    verify_bot_check(body)
    email = body.email.strip().lower()
    with closing(_conn()) as c, c:
        row = c.execute("SELECT id,pw_salt,pw_hash FROM users WHERE email=?", (email,)).fetchone()
        # same work whether or not the user exists, so timing doesn't reveal which emails have accounts
        salt, stored = (row[1], row[2]) if row else (b"0" * 16, b"\0" * 32)
        ok = hmac.compare_digest(_hash_pw(body.password, salt), stored)
        if not (row and ok):
            raise ValueError("Wrong email or password.")
        token = _new_session(c, row[0])
        user = c.execute("SELECT id,email,name,prefs FROM users WHERE id=?", (row[0],)).fetchone()
    return token, _public(user)


def user_for(token: str | None) -> dict | None:
    if not token:
        return None
    with closing(_conn()) as c:
        row = c.execute("SELECT u.id,u.email,u.name,u.prefs FROM sessions s JOIN users u ON u.id=s.user_id "
                        "WHERE s.token_hash=? AND s.expires>?", (_token_hash(token), time.time())).fetchone()
    return _public(row) if row else None


def log_out(token: str) -> None:
    with closing(_conn()) as c, c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def save_prefs(user_id: int, prefs: Prefs) -> dict:
    with closing(_conn()) as c, c:
        c.execute("UPDATE users SET prefs=? WHERE id=?", (prefs.model_dump_json(), user_id))
        row = c.execute("SELECT id,email,name,prefs FROM users WHERE id=?", (user_id,)).fetchone()
    return _public(row)


def _check_strength(password: str) -> None:
    if password.lower() in {"password", "12345678", "loremaster"} or len(set(password)) < 4:
        raise ValueError("Please choose a less guessable password.")


def _verify(c: sqlite3.Connection, user_id: int, password: str) -> None:
    salt, stored = c.execute("SELECT pw_salt,pw_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if not hmac.compare_digest(_hash_pw(password, salt), stored):
        raise ValueError("Your current password isn't right.")


def change_password(user_id: int, token: str, body: PasswordChange) -> None:
    """Verify the current password, store the new one (fresh salt) and sign out every OTHER session."""
    _check_strength(body.new)
    if body.new == body.current:
        raise ValueError("The new password must be different.")
    with closing(_conn()) as c, c:
        _verify(c, user_id, body.current)
        salt = secrets.token_bytes(16)
        c.execute("UPDATE users SET pw_salt=?, pw_hash=? WHERE id=?", (salt, _hash_pw(body.new, salt), user_id))
        c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, _token_hash(token)))


def rename(user_id: int, name: str) -> dict:
    with closing(_conn()) as c, c:
        c.execute("UPDATE users SET name=? WHERE id=?", (name.strip(), user_id))
        row = c.execute("SELECT id,email,name,prefs FROM users WHERE id=?", (user_id,)).fetchone()
    return _public(row)


def log_out_everywhere(user_id: int, token: str) -> int:
    with closing(_conn()) as c, c:
        return c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, _token_hash(token))).rowcount


def delete_account(user_id: int, password: str) -> None:
    with closing(_conn()) as c, c:
        _verify(c, user_id, password)
        c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
