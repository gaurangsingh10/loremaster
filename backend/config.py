"""Every knob in one place: paths, .env lookup, model, prices, budgets and limits."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent

# Course rule: look for .env in the repo folder first, then the folder above it
# (where the teaching staff keep theirs). The repo's .env wins over the parent's, and a .env file wins over a
# key exported in the shell (so updating .env always takes effect, even if an old key lives in ~/.zshrc).
FILE_ENV: dict[str, str] = {}             # keys found in .env files (these beat anything exported in the shell)
for folder in (REPO.parent, REPO):          # parent first, then repo (later loads override earlier ones)
    if (folder / ".env").exists():
        load_dotenv(folder / ".env", override=True)
        FILE_ENV.update({k: v for k, v in dotenv_values(folder / ".env").items() if v})


def _key(name: str) -> str:
    return (FILE_ENV.get(name) or os.getenv(name, "")).strip()


# Which provider to call gpt-6-luna through:
#   1) PORTKEY_API_KEY in a .env file  -> the course Portkey gateway (graders' setup)
#   2) OPENAI_API_KEY in a .env file   -> OpenAI directly (course rule: your own key must be named OPENAI_API_KEY)
#   3) otherwise whatever is exported in the shell, Portkey first.
def provider() -> str:
    if FILE_ENV.get("PORTKEY_API_KEY"):
        return "portkey"
    if FILE_ENV.get("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("PORTKEY_API_KEY", "").strip():
        return "portkey"
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "openai"
    return "none"

PROMPTS_DIR = BACKEND / "prompts"
PACKS_DIR = BACKEND / "source_packs"
DATA = REPO / "data"
CACHE_DIR = DATA / "cache"
PAGES_DIR = CACHE_DIR / "pages"
EPISODES_DIR = CACHE_DIR / "episodes"
FIXTURES_DIR = DATA / "fixtures"
AUDIO_DIR = DATA / "audio"
DB_PATH = DATA / "loremaster.db"
OUTPUT = REPO / "output"
AUDIT_PATH = OUTPUT / "audit_trail.json"
USAGE_LOG_PATH = OUTPUT / "usage_log.json"

# Course rule: course key + gpt-6-luna only. Deliberately NOT overridable by a MODEL_NAME env var.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# Live = fetch wikis (and save what we fetch into data/cache/pages)
# Cached = only use pages already in data/cache/pages (bundled test dataset, no network)
# Demo = no model calls at all; play the bundled sample episode (works with no key)
DATA_MODE = os.getenv("LOREMASTER_DATA_MODE", "live").strip().lower()

# --- Prices: OpenAI Standard tier, USD per 1M tokens (Lecture 11 slides, Oct 2026) -------------------
PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached_input": 0.01, "cache_write": 0.125, "output": 0.50},
}
# Optional natural voice (only when OPENAI_API_KEY is set; Portkey course key has no TTS deployment).
TTS_MODEL = "gpt-4o-mini-tts"
TTS_USD_PER_1K_CHARS = 0.015  # estimate (published per-minute pricing ~ $0.015/min ≈ 1K chars); labelled as estimate

# --- Budgets & limits (safety: overspending and loops) ---------------------------------------------
EPISODE_BUDGET_USD = 0.05          # hard cap per episode, across every agent and every chapter
REQUEST_LIMIT_PER_AGENT_RUN = 10    # model calls inside one agent run (tool loop)
TOOL_CALLS_LIMIT_PER_AGENT_RUN = 14
TOTAL_TOKENS_LIMIT_PER_AGENT_RUN = 60_000
MAX_OUTPUT_TOKENS = 4_000           # per model response
MAX_REVISIONS_PER_CHAPTER = 1       # Skeptic -> Storyteller rewrite loop
MAX_CARDS_PER_CHAPTER = 8
CARD_CHARS = 400                    # each evidence snippet is capped
PAGE_CHARS = 60_000                 # sanitized page text cap before paragraph scoring
MAX_TOPIC_CHARS = 300
RATE_LIMIT_EPISODES = 5             # per client per window
RATE_LIMIT_WINDOW_S = 600
WIKI_TIMEOUT_S = 12

WORDS_PER_MINUTE = 150              # spoken narration pace
LENGTHS = {10: 2, 20: 4, 40: 8}     # minutes -> chapters

# Wikimedia's robot policy requires a descriptive agent with a contact URL.
USER_AGENT = "Loremaster/0.1 (https://github.com/gaurangsingh10/loremaster; MGT 409 student project) httpx"


def require_api_key() -> str:
    p = provider()
    if p == "none":
        raise RuntimeError(
            "No API key: put PORTKEY_API_KEY (course key) or OPENAI_API_KEY (your own) in a .env file in the repo "
            "folder or the folder above it (or switch to Demo mode: LOREMASTER_DATA_MODE=demo)."
        )
    return _key("PORTKEY_API_KEY" if p == "portkey" else "OPENAI_API_KEY")


def has_api_key() -> bool:
    return provider() != "none"


def openai_tts_key() -> str | None:
    return _key("OPENAI_API_KEY") or None


@lru_cache(maxsize=1)
def build_model():
    # gpt-6-luna rejects function tools on /chat/completions, so use the Responses API (HW5 lesson).
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if provider() == "openai":  # your own OpenAI key: call OpenAI directly (no gateway headers)
        client = AsyncOpenAI(api_key=require_api_key(), timeout=120)
        return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    client = AsyncOpenAI(
        api_key=require_api_key(),
        base_url=PORTKEY_BASE_URL,
        # Portkey's gateway response cache would replay an identical earlier answer (same episode for every listener,
        # and copied usage that breaks cost measurement). Force fresh generations; OpenAI prompt caching still applies.
        default_headers={"x-portkey-provider": "openai", "x-portkey-cache-force-refresh": "true"},
        timeout=120,
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
