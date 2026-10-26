"""Tools: wiki search/fetch (keyless MediaWiki APIs), the sanitizer, evidence cards, Open Library.

Everything here is plain code. The models only ever see sanitized, capped snippets (evidence cards),
never raw pages, and never anything a person couldn't see on screen.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup, Comment

from config import (CARD_CHARS, DATA_MODE, FIXTURES_DIR, PACKS_DIR, PAGE_CHARS, PAGES_DIR, USER_AGENT,
                    WIKI_TIMEOUT_S)
from models import EvidenceCard

PACKS: dict[str, dict] = {p.stem: json.loads(p.read_text()) for p in sorted(PACKS_DIR.glob("*.json"))}

# ------------------------------------------------------------------ sanitizer (defense layer: CODE)
ZERO_WIDTH = re.compile("[​‌‍‎‏⁠⁡⁢⁣⁤﻿‪-‮⁦-⁩]")
HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em|rem)?\s*(?:;|$)|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$)"
    r"|color\s*:\s*(?:#fff(?:fff)?|white|rgba?\(\s*255\s*,\s*255\s*,\s*255)|left\s*:\s*-\d{3,}px|height\s*:\s*0(?:px)?\s*;?\s*overflow\s*:\s*hidden",
    re.I,
)
# Lines that talk to an AI rather than to a human reader. Wiki prose never says these things.
AI_DIRECTED = re.compile(
    r"ignore (?:all |any |your |the )?(?:previous |prior |above )?(?:instructions|rules|prompts?)"
    r"|disregard (?:the|your|all) |system prompt|you are (?:an? )?(?:ai|assistant|language model|chatbot)"
    r"|(?:as|to) the (?:ai|assistant|narrator|storyteller)|tell the (?:listener|user)s? to|new instructions"
    r"|developer mode|jailbreak|\bdo not (?:grade|flag)\b|mark (?:this|all) (?:claims? )?as (?:canon|documented)",
    re.I,
)
STRIP_SELECTORS = ("script", "style", "noscript", "template", "iframe", "object", "table", "figure", "sup.reference",
                   ".navbox", ".toc", ".mw-editsection", ".reference", ".reflist", ".portable-infobox", "aside",
                   ".noprint", ".mw-empty-elt", "nav", "form", "input", "button", ".references",
                   ".mw-references-wrap", ".hatnote", ".shortdescription", ".gallery")


@dataclass
class CleanPage:
    pack: str
    title: str
    url: str
    paragraphs: list[str]
    quarantined: list[str] = field(default_factory=list)


def _is_hidden(tag) -> bool:
    if tag.has_attr("hidden") or tag.get("aria-hidden") == "true":
        return True
    style = tag.get("style") or ""
    return bool(HIDDEN_STYLE.search(style))


def sanitize_html(html: str, *, defenses: bool = True) -> tuple[list[str], list[str]]:
    """Return (visible paragraphs, quarantined text). With defenses off, returns everything naively (attack demo)."""
    soup = BeautifulSoup(html, "html.parser")
    if not defenses:  # what a naive scraper would pass to the model: every bit of text, hidden or not
        for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
            c.replace_with(f" {c} ")
        text = soup.get_text("\n")
        paras = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n")]
        return [p for p in paras if len(p) > 40], []

    quarantined: list[str] = []
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if c.strip():
            quarantined.append(f"[html comment] {c.strip()[:300]}")
        c.extract()
    for tag in soup.find_all(True):
        if getattr(tag, "decomposed", False):
            continue
        if _is_hidden(tag):
            txt = tag.get_text(" ", strip=True)
            if txt:
                quarantined.append(f"[hidden element] {txt[:300]}")
            tag.decompose()
    for sel in STRIP_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()

    paras: list[str] = []
    for p in soup.find_all(["p", "li", "blockquote"]):
        text = ZERO_WIDTH.sub("", p.get_text(" ", strip=True))
        text = re.sub(r"\[\d+\]|\[citation needed\]|\[edit\]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 60 or text.startswith(("^", "Retrieved", "Archived")):
            continue
        kept = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if AI_DIRECTED.search(sentence):
                quarantined.append(f"[ai-directed text] {sentence[:300]}")
            else:
                kept.append(sentence)
        text = " ".join(kept).strip()
        if len(text) >= 60:
            paras.append(text)
    total, out = 0, []
    for p in paras:
        if total > PAGE_CHARS:
            break
        out.append(p)
        total += len(p)
    return out, quarantined


# ------------------------------------------------------------------ wiki access (live / cached)
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:90] or "x"


def _cache_path(pack: str, kind: str, key: str) -> Path:
    return PAGES_DIR / pack / f"{kind}__{_slug(key)}.json"


def _cache_get(pack: str, kind: str, key: str):
    p = _cache_path(pack, kind, key)
    return json.loads(p.read_text()) if p.exists() else None


def _cache_put(pack: str, kind: str, key: str, value) -> None:
    p = _cache_path(pack, kind, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False))


def page_url(pack: str, title: str) -> str:
    return PACKS[pack]["page_url"].format(title=quote(title.replace(" ", "_")))


async def _api_get(pack: str, params: dict) -> dict:
    api = PACKS[pack]["api"]
    async with httpx.AsyncClient(timeout=WIKI_TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
        r = await c.get(api, params={**params, "format": "json", "formatversion": 2})
        r.raise_for_status()
        return r.json()


def _cached_titles(pack: str) -> list[str]:
    folder = PAGES_DIR / pack
    titles = []
    for p in folder.glob("page__*.json") if folder.exists() else []:
        try:
            titles.append(json.loads(p.read_text())["title"])
        except Exception:
            pass
    return titles


def _offline_search(pack: str, query: str, limit: int) -> list[dict]:
    words = set(_words(query))
    scored = []
    for t in _cached_titles(pack):
        page = _cache_get(pack, "page", t) or {}
        blob = (t + " " + page.get("html", "")[:20000]).lower()
        score = sum(blob.count(w) for w in words) + 5 * sum(w in t.lower() for w in words)
        if score:
            scored.append((score, t))
    scored.sort(reverse=True)
    return [{"title": t, "snippet": "(cached page)"} for _, t in scored[:limit]]


async def search_wiki(pack: str, query: str, limit: int = 5, mode: str | None = None) -> list[dict]:
    mode = mode or DATA_MODE
    if pack not in PACKS:
        raise ValueError(f"unknown source pack {pack!r}")
    cached = _cache_get(pack, "search", query)
    if mode == "cached" or mode == "demo":
        return cached or _offline_search(pack, query, limit)
    try:
        data = await _api_get(pack, {"action": "query", "list": "search", "srsearch": query, "srlimit": limit,
                                     "srprop": "snippet"})
        hits = [{"title": h["title"], "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", ""))[:200]
                 or "(this wiki gives no preview; use read_page to see the text)"}
                for h in data.get("query", {}).get("search", [])]
        _cache_put(pack, "search", query, hits)
        return hits
    except Exception:
        return cached or _offline_search(pack, query, limit)  # network trouble -> fall back to bundled cache


async def fetch_page_html(pack: str, title: str, mode: str | None = None) -> dict | None:
    mode = mode or DATA_MODE
    cached = _cache_get(pack, "page", title)
    if cached or mode in ("cached", "demo"):
        return cached
    try:
        data = await _api_get(pack, {"action": "parse", "page": title, "prop": "text", "redirects": 1,
                                     "disablelimitreport": 1, "disableeditsection": 1})
        parse = data.get("parse") or {}
        html = parse.get("text") or ""
        if not html:
            return None
        real_title = parse.get("title", title)
        value = {"pack": pack, "title": real_title, "url": page_url(pack, real_title), "html": html}
        _cache_put(pack, "page", title, value)
        if real_title != title:
            _cache_put(pack, "page", real_title, value)
        return value
    except Exception:
        return None


def load_fixture(name: str) -> dict:
    """Local test pages for the Safety Lab (e.g. the poisoned wiki page)."""
    meta = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
    meta["html"] = (FIXTURES_DIR / meta["file"]).read_text()
    return meta


# ------------------------------------------------------------------ evidence cards
STOP = set("""a an the and or of to in on for with by from as at is are was were be been being that this these those it its
into than then there their they them he she his her who whom which what when where why how not no but if so such
about over under between after before during also more most other some any all can could would should may might
did does do had has have i you we our your my me us vs via""".split())


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP and len(w) > 2]


def _trim(text: str, limit: int = CARD_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[: end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + " …").strip()


def best_paragraphs(paragraphs: list[str], focus: str, k: int = 3) -> list[str]:
    """Keyword-scored retrieval (Lecture 10 pattern): cheap, deterministic, no model call."""
    fw = _words(focus)
    if not fw:
        return paragraphs[:k]
    weights = {w: 1.0 / (1 + sum(w in p.lower() for p in paragraphs)) for w in set(fw)}  # rare words count more
    scored = []
    for i, p in enumerate(paragraphs):
        pl = p.lower()
        s = sum(weights[w] for w in set(fw) if w in pl) + (0.2 if i < 3 else 0)  # lead paragraphs get a nudge
        scored.append((s, i, p))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [p for s, _, p in scored[:k] if s > 0.05]


class CardRegistry:
    """Code (not the model) assigns evidence ids, so a model can never cite a card that doesn't exist."""

    def __init__(self, prefix: str = "E", seed: list[EvidenceCard] | None = None) -> None:
        self.cards: dict[str, EvidenceCard] = {c.id: c for c in (seed or [])}
        self._seen: set[tuple[str, str]] = {(c.page_title, c.snippet[:80]) for c in (seed or [])}
        self.prefix = prefix
        self._n = 0

    def add(self, pack: str, title: str, url: str, snippet: str, license_: str) -> EvidenceCard | None:
        key = (title, snippet[:80])
        if key in self._seen:
            return None
        self._seen.add(key)
        self._n += 1
        cid = f"{self.prefix}{self._n}" if self.prefix != "E" else f"E{len(self.cards) + 1}"
        card = EvidenceCard(id=cid, pack=pack, page_title=title, url=url, snippet=_trim(snippet), license=license_)
        self.cards[cid] = card
        return card


# ------------------------------------------------------------------ Open Library (Librarian)
async def search_open_library(query: str, limit: int = 5) -> list[dict]:
    cached = _cache_get("openlibrary", "search", query)
    if DATA_MODE in ("cached", "demo"):
        return cached or []
    try:
        async with httpx.AsyncClient(timeout=WIKI_TIMEOUT_S, headers={"User-Agent": USER_AGENT}) as c:
            r = await c.get("https://openlibrary.org/search.json",
                            params={"q": query, "limit": limit, "fields": "title,author_name,first_publish_year,key"})
            r.raise_for_status()
            docs = r.json().get("docs", [])
        out = [{"title": d.get("title", ""), "author": ", ".join(d.get("author_name", [])[:2]),
                "year": d.get("first_publish_year"), "url": f"https://openlibrary.org{d.get('key', '')}"} for d in docs]
        _cache_put("openlibrary", "search", query, out)
        return out
    except Exception:
        return cached or []
