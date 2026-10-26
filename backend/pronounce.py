"""Pronunciation help for the narrator: spell out abbreviations, and give hand-written phonemes (IPA, espeak style)
for history and lore names the default phonemizer gets wrong. Checked by reading the phoneme output, word by word."""

from __future__ import annotations

import re

# Text-level fixes before phonemizing.
ABBREV = [
    (re.compile(r"\bBBY\b"), "xbbyx"), (re.compile(r"\bABY\b"), "xabyx"), (re.compile(r"\bAD\b"), "xadx"),
    (re.compile(r"\bBCE\b"), "B C E"), (re.compile(r"\bCE\b"), "C E"), (re.compile(r"\b40K\b", re.I), "forty K"),
    (re.compile(r"\bM(\d{1,2})\b"), r"M \1"), (re.compile(r"\be\.g\.", re.I), "for example"),
    (re.compile(r"\bi\.e\.", re.I), "that is"), (re.compile(r"\bvs\.?\b", re.I), "versus"), (re.compile(r"&"), " and "),
    (re.compile(r"\s*[—–]\s*"), ", "), (re.compile(r"…"), "..."), (re.compile(r"[“”]"), '"'), (re.compile(r"[‘’]"), "'"),
]

# word (case-insensitive, whole word) -> IPA. One entry serves both UK and US accents.
LEXICON: dict[str, str] = {
    "xbbyx": "bˌiː bˌiː wˈaɪ", "xabyx": "ˌeɪ bˌiː wˈaɪ", "xadx": "ˌeɪ dˈiː",
    "astartes": "ɐstˈɑːteɪz", "custodes": "kʌstˈəʊdeɪz", "custodian": "kʌstˈəʊdiən", "custodians": "kʌstˈəʊdiənz",
    "vandire": "vandˈɪə", "jaghatai": "dʒˈaɡɐtaɪ", "omnissiah": "ˌɒmnɪsˈaɪə", "astra militarum": "ˈastɹə mˌɪlɪtˈɑːɹəm",
    "valdor": "vˈaldɔː", "horus": "hˈɔːɹəs", "lorgar": "lˈɔːɡɑː", "sigismund": "sˈɪɡɪsmʊnd", "khorne": "kˈɔːn",
    "siete partidas": "siˈɛte paɹtˈiːdas", "siete": "siˈɛte", "partidas": "paɹtˈiːdas", "fuero juzgo": "fwˈeɹəʊ hˈuːθɡəʊ",
    "fuero real": "fwˈeɹəʊ ɹeɪˈɑːl", "gananciales": "ɡananθiˈaːles", "liber iudiciorum": "lˈiːbɛɹ jˌuːdɪkiˈɔːɹʊm",
    "chindasuinth": "kˈɪndɐswɪnθ", "reconquista": "ɹˌeɪkɒnkˈiːstə", "alfonso": "alfˈɒnsəʊ", "castile": "kastˈiːl",
    "ptolemaic": "tˌɒlɪmˈeɪɪk", "ptolemy": "tˈɒləmi", "ptolemies": "tˈɒləmiz", "ugarit": "ˈuːɡɑːɹɪt",
    "mycenae": "maɪsˈiːniː", "mycenaean": "mˌaɪsɪnˈiːən", "ramesses": "ɹˈamɪsiːz", "serapeum": "sˌɛɹɐpˈiːəm",
    "princeps": "pɹˈɪŋkɛps", "imperator": "ˌɪmpəɹˈɑːtɔː", "perpetuo": "pɛɹpˈɛtuːəʊ", "agoge": "ɐɡˈəʊɡiː",
    "basileus": "bˌasɪlˈeɪəs", "domus aurea": "dˈɒmʊs ˈaʊɹeɪə", "gracchi": "ɡɹˈakiː", "sulla": "sˈʊlə",
    "suetonius": "swiːtˈəʊniəs", "tacitus": "tˈasɪtəs", "boudicca": "bˈuːdɪkə", "hypatia": "haɪpˈeɪʃə",
    "sifo-dyas": "sˈaɪfəʊ dˈaɪəs", "de molay": "də mɒlˈeɪ", "molay": "mɒlˈeɪ", "yavin": "jˈavɪn",
    "khagan": "kˈɑːɡɑːn", "khan": "kˈɑːn", "varangian": "vɐɹˈandʒiən", "varangians": "vɐɹˈandʒiənz",
    "palpatine": "pˈalpətiːn", "naboo": "nˈɑːbuː", "kamino": "kəmˈiːnəʊ", "ewoks": "ˈiːwɒks", "endor": "ˈɛndɔː",
}
_LEX_RE = re.compile(r"\b(" + "|".join(sorted((re.escape(k) for k in LEXICON), key=len, reverse=True)) + r")('s|s)?\b", re.I)


def normalize(text: str) -> str:
    for pat, rep in ABBREV:
        text = pat.sub(rep, text)
    return re.sub(r"[ \t]+", " ", text).strip()


def to_phonemes(text: str, phonemize, lang: str) -> str:
    """Phonemize normal text with the engine's phonemizer; splice in lexicon IPA for known names."""
    text = normalize(text)
    out, last = [], 0
    for m in _LEX_RE.finditer(text):
        if m.start() > last:
            out.append(phonemize(text[last:m.start()], lang))
        out.append(LEXICON[m.group(1).lower()] + ("z" if m.group(2) else ""))  # possessive / plural
        last = m.end()
    if last < len(text):
        out.append(phonemize(text[last:], lang))
    return re.sub(r"\s+", " ", " ".join(p.strip() for p in out if p.strip()))
