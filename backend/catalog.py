"""Curated starter threads (shown first on the menu) and pack selection for free-text topics."""

from __future__ import annotations

import re

from models import Mode, Thread

CURATED: list[Thread] = [
    Thread(id="texas-law-medieval-spain", title="Texas Law & Medieval Spain",
           hook="Why a Texas divorce court still splits property like a Visigothic king, and the 'Muslim Spain' legend.",
           mode="history", packs=["history"], era="Visigothic & Castilian Spain → Spanish Texas", universe="", curated=True),
    Thread(id="rome-imperium", title="Rome → Imperium of Man",
           hook="Late Rome, Byzantium and the Inquisition built the galaxy's grimmest empire.",
           mode="crossover", packs=["history", "warhammer40k"], era="Late Roman Empire & Byzantium",
           universe="Warhammer 40,000", curated=True),
    Thread(id="republic-galactic-empire", title="Roman Republic → Galactic Empire",
           hook="Caesar, Augustus and emergency powers: Lucas didn't have to invent Palpatine's playbook.",
           mode="crossover", packs=["history", "star_wars"], era="Late Roman Republic",
           universe="Star Wars", curated=True),
    Thread(id="crusades-space-marines", title="Crusades → Space Marines",
           hook="Templars, Hospitallers and the warrior-monk ideal behind the Adeptus Astartes.",
           mode="crossover", packs=["history", "warhammer40k"], era="The Crusades & military orders",
           universe="Warhammer 40,000", curated=True),
]
BY_ID = {t.id: t for t in CURATED}

SW = re.compile(r"star ?wars|jedi|sith|palpatine|skywalker|vader|galactic (republic|empire|senate)|mandalor|clone wars|yoda|wookiee", re.I)
WH = re.compile(r"40k|40,000|warhammer|imperium of man|space marines?|astartes|primarch|horus|emperor of mankind|inquisition of|chaos gods|eldar|aeldari|ork|necron|tyranid|adeptus", re.I)


SCI = re.compile(r"\b(science|scientist|physics|chemistry|biology|evolution|gene|dna|vaccine|placebo|brain|einstein|newton|darwin|quantum|climate|medicine|disease|astronomy|universe|atom)\b", re.I)
TECH = re.compile(r"\b(technology|internet|computer|software|ai|artificial intelligence|telegraph|telephone|radio|printing press|invent\w*|edison|tesla|engine|railway|silicon|chip|smartphone|rocket)\b", re.I)
POL = re.compile(r"\b(politic\w*|democracy|constitution|parliament|senate|congress|election|vote|filibuster|federalist|revolution|government|law|supreme court|monarchy|republic|socialism|liberalism|treaty)\b", re.I)


def genre_pack(topic: str) -> str:
    """Nonfiction topics use Wikipedia with genre-specific grading rules."""
    if SCI.search(topic):
        return "science"
    if TECH.search(topic):
        return "technology"
    if POL.search(topic):
        return "politics"
    return "history"


def packs_for(topic: str, mode: Mode) -> list[str]:
    universes = (["star_wars"] if SW.search(topic) else []) + (["warhammer40k"] if WH.search(topic) else [])
    if mode == "history":
        return [genre_pack(topic)]
    if mode == "lore":
        return universes[:1] or ["warhammer40k"]
    return [genre_pack(topic)] + (universes[:1] or ["star_wars"])


def thread_from_topic(topic: str, mode: Mode) -> Thread:
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:48] or "custom"
    packs = packs_for(topic, mode)
    universe = {"star_wars": "Star Wars", "warhammer40k": "Warhammer 40,000"}.get(packs[-1], "")
    genre = "lore" if mode == "lore" else packs[0]
    return Thread(id=f"custom-{slug}", title=topic.strip()[:80], hook=f"A listener asked: {topic.strip()[:140]}",
                  mode=mode, packs=packs, universe=universe if mode != "history" else "", curated=False, genre=genre)
