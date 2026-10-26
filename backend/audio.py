"""Narration audio as real files, played as a per-paragraph playlist (first paragraph ready in ~3 s).

Engine priority (first that works on this machine):
  1. Kokoro (neural, free, offline): needs models/kokoro-v1.0.onnx + models/voices-v1.0.bin (see README)
  2. OpenAI TTS: if OPENAI_API_KEY is set (paid)
  3. macOS `say` + afconvert: built into every Mac
  4. Windows SAPI: via PowerShell System.Speech
  5. none: the frontend falls back to the browser's Web Speech API
Every segment is cached in data/audio/, so replays are free and instant. A chapter's segments are pre-rendered
in the background as soon as the chapter is written.
"""

from __future__ import annotations

import asyncio
import hashlib
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import httpx

from config import AUDIO_DIR, REPO, TTS_MODEL, openai_tts_key

MODELS = REPO / "models"
KOKORO_MODEL, KOKORO_VOICES = MODELS / "kokoro-v1.0.onnx", MODELS / "voices-v1.0.bin"
# Voice id = "<gender>-<accent>-<tone>", e.g. "male-uk-deep". Speakers chosen for clarity in long narration.
SPEAKERS = {("male", "uk"): "bm_george", ("female", "uk"): "bf_emma", ("male", "us"): "am_michael", ("female", "us"): "af_heart"}
LANGS = {"uk": "en-gb", "us": "en-us"}
# tone -> (speaking speed, pitch factor). "deep" plays the audio ~7% lower: deeper AND slightly slower.
TONES = {"deep": (0.94, 0.93), "natural": (0.98, 1.0)}
LEGACY = {"george": "male-uk-deep", "lewis": "male-uk-natural", "fable": "male-uk-natural", "onyx": "male-us-deep", "archivist": "male-uk-deep"}
DEFAULT_VOICE = "male-uk-deep"


def parse_voice(voice: str) -> tuple[str, str, str]:
    voice = LEGACY.get(voice, voice)
    parts = (voice or DEFAULT_VOICE).split("-")
    g = parts[0] if parts and parts[0] in ("male", "female") else "male"
    a = parts[1] if len(parts) > 1 and parts[1] in LANGS else "uk"
    t = parts[2] if len(parts) > 2 and parts[2] in TONES else "deep"
    return g, a, t


def voice_label(voice: str) -> str:
    g, a, t = parse_voice(voice)
    return f"{'UK' if a == 'uk' else 'US'} {'man' if g == 'male' else 'woman'}{' · deep' if t == 'deep' else ''}"
MAC_VOICE, MAC_RATE = "Daniel", 180
MEDIA = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


def clean_text(narration: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\s*\[c\d+\]", "", narration)).strip()


def segment_map(narration: str, min_chars: int = 220) -> list[tuple[str, list[int]]]:
    """Split narration into paragraph-sized pieces (short paragraphs merged), keeping which paragraphs each covers.
    Paragraph indices match the frontend's narration.split(/\n+/) (blank lines dropped)."""
    raw = [p for p in narration.split("\n") if p.strip()]
    out: list[tuple[str, list[int]]] = []
    for i, p in enumerate(raw):
        text = clean_text(p)
        if out and len(out[-1][0]) < min_chars:
            out[-1] = (out[-1][0] + " " + text, out[-1][1] + [i])
        else:
            out.append((text, [i]))
    # Make the FIRST section short (one or two sentences) so playback starts within a couple of seconds.
    if out and len(out[0][0]) > 260:
        text, paras = out[0]
        sents = re.split(r"(?<=[.!?])\s+", text)
        head, rest = "", []
        for k, snt in enumerate(sents):
            if head and len(head) + len(snt) > 180:
                rest = sents[k:]
                break
            head = (head + " " + snt).strip()
        if rest:
            out[0:1] = [(head, paras), (" ".join(rest), paras)]
    return out or [(clean_text(narration), [0])]


def segments(narration: str) -> list[str]:
    return [t for t, _ in segment_map(narration)]


def kokoro_available() -> bool:
    if not (KOKORO_MODEL.exists() and KOKORO_VOICES.exists()):
        return False
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except ImportError:
        return False


def engine() -> str:
    if kokoro_available():
        return "kokoro"
    if openai_tts_key():
        return "openai"
    if platform.system() == "Darwin" and shutil.which("say") and shutil.which("afconvert"):
        return "macos"
    if platform.system() == "Windows" and shutil.which("powershell"):
        return "windows"
    return "none"


def voices() -> list[dict]:
    if engine() != "kokoro":
        return []
    return [{"id": f"{g}-{a}-{t}", "label": voice_label(f"{g}-{a}-{t}")}
            for a in ("uk", "us") for g in ("male", "female") for t in ("deep", "natural")]


# ------------------------------------------------------------------ engines
_kokoro = None
_kokoro_lock = threading.Lock()  # one ONNX session, used from worker threads one at a time


def _render_kokoro(text: str, out: Path, voice: str) -> None:
    global _kokoro
    import soundfile as sf
    import pronounce
    g, a, t = parse_voice(voice)
    speed, pitch = TONES[t]
    lang = LANGS[a]
    with _kokoro_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro
            _kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
        phonemes = pronounce.to_phonemes(text, _kokoro.tokenizer.phonemize, lang)  # lexicon + abbreviations
        samples, sr = _kokoro.create(phonemes, voice=SPEAKERS[(g, a)], speed=speed, lang=lang, is_phonemes=True,
                                     sentence_pause=0.35, clause_pause=0.15)   # a beat longer between sentences
    wav = out.with_suffix(".wav")
    sf.write(str(wav), samples, int(sr * pitch))   # play back a touch slower: lower pitch, slower pace
    _to_m4a_if_possible(wav, out)


def _to_m4a_if_possible(wav: Path, out: Path) -> None:
    if out.suffix == ".m4a" and shutil.which("afconvert"):
        try:  # ~10x smaller than WAV; if conversion fails we simply keep the WAV
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(wav), str(out)], check=True, timeout=120,
                           capture_output=True)
            wav.unlink(missing_ok=True)
        except Exception:
            out.unlink(missing_ok=True)
    elif out.suffix != ".wav":
        wav.rename(out.with_suffix(".wav"))


def _render_macos(text: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        txt, aiff = Path(td) / "n.txt", Path(td) / "n.aiff"
        txt.write_text(text)
        voices_list = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
        v = ["-v", MAC_VOICE] if re.search(rf"^{MAC_VOICE}\s", voices_list, re.M) else []
        subprocess.run(["say", *v, "-r", str(MAC_RATE), "-f", str(txt), "-o", str(aiff)], check=True, timeout=300)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(aiff), str(out)], check=True, timeout=120)


def _render_windows(text: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        txt = Path(td) / "n.txt"
        txt.write_text(text, encoding="utf-8")
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = 1; $s.SetOutputToWaveFile('{out}'); $s.Speak([IO.File]::ReadAllText('{txt}')); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=300)


async def _render_openai(text: str, out: Path) -> None:
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post("https://api.openai.com/v1/audio/speech", headers={"Authorization": f"Bearer {openai_tts_key()}"},
                         json={"model": TTS_MODEL, "voice": "onyx", "input": text[:4000],
                               "instructions": "A deep baritone history lecturer with a warm British accent. Passionate, measured, dramatic."})
        r.raise_for_status()
        out.write_bytes(r.content)


# ------------------------------------------------------------------ cache + public API
_locks: dict[str, asyncio.Lock] = {}
_engine_lock: asyncio.Lock | None = None   # one render at a time (Kokoro is CPU-bound)
_demand = 0                                # renders a listener is actively waiting for: they jump the queue


def warm_up() -> None:
    """Load the Kokoro model at server start so the first Play doesn't pay a ~3 s cold start."""
    global _kokoro
    if engine() == "kokoro" and _kokoro is None:
        with _kokoro_lock:
            if _kokoro is None:
                from kokoro_onnx import Kokoro
                _kokoro = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))


def _key(narration: str, seg: int, voice: str, eng: str) -> str:
    # Keyed by the narration's CONTENT, so the same chapter (instant stories, demo, replays) shares one cache.
    h = hashlib.sha1(clean_text(narration).encode()).hexdigest()[:14]
    return f"{h}_{seg}_{eng}{'-' + '-'.join(parse_voice(voice)) if eng == 'kokoro' else ''}-v2"


def _cached(key: str) -> Path | None:
    for ext in (".m4a", ".mp3", ".wav"):
        p = AUDIO_DIR / f"{key}{ext}"
        if p.exists() and p.stat().st_size > 1000:
            return p
    return None


async def render_segment(eid: str, chapter: int, seg: int, narration: str, voice: str = DEFAULT_VOICE,
                         background: bool = False) -> Path | None:
    global _engine_lock, _demand
    eng = engine()
    segs = segments(narration)
    if eng == "none" or not (0 <= seg < len(segs)):
        return None
    key = _key(narration, seg, voice, eng)
    if p := _cached(key):
        return p
    lock = _locks.setdefault(key, asyncio.Lock())
    _engine_lock = _engine_lock or asyncio.Lock()
    if not background:
        _demand += 1
    try:
        if background:
            while _demand > 0:          # let the listener's request go first
                await asyncio.sleep(0.05)
        async with lock, _engine_lock:
            return await _render_locked(key, eng, segs[seg], voice)
    finally:
        if not background:
            _demand -= 1


async def render_whole(text: str, voice: str = DEFAULT_VOICE) -> Path | None:
    """Render a short text (an Ask or Interview answer) as ONE clip. Unlike render_segment, it is never split, so
    the listener hears every sentence, not just the quick-start first piece."""
    global _engine_lock, _demand
    eng = engine()
    text = clean_text(" ".join(t for t in text.split("\n") if t.strip()))
    if eng == "none" or not text:
        return None
    key = "w" + _key(text, 0, voice, eng)
    lock = _locks.setdefault(key, asyncio.Lock())
    _engine_lock = _engine_lock or asyncio.Lock()
    _demand += 1
    try:
        async with lock, _engine_lock:
            return await _render_locked(key, eng, text, voice)
    finally:
        _demand -= 1


async def _render_locked(key: str, eng: str, text: str, voice: str) -> Path | None:
        if p := _cached(key):
            return p
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        mac = platform.system() == "Darwin" and bool(shutil.which("afconvert"))
        try:
            if eng == "kokoro":
                out = AUDIO_DIR / f"{key}{'.m4a' if mac else '.wav'}"
                await asyncio.to_thread(_render_kokoro, text, out, voice)
            elif eng == "openai":
                out = AUDIO_DIR / f"{key}.mp3"
                await _render_openai(text, out)
            elif eng == "macos":
                out = AUDIO_DIR / f"{key}.m4a"
                await asyncio.to_thread(_render_macos, text, out)
            else:
                out = AUDIO_DIR / f"{key}.wav"
                await asyncio.to_thread(_render_windows, text, out)
            return _cached(key)
        except Exception:
            return None


async def prerender(eid: str, chapter: int, narration: str, voice: str = DEFAULT_VOICE) -> None:
    """Render every segment of a chapter in order (background task)."""
    for i in range(len(segments(narration))):
        await render_segment(eid, chapter, i, narration, voice, background=True)
