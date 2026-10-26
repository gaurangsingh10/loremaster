"""Loremaster API. Run from backend/:  uvicorn main:app --reload --port 8000"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import defaultdict, deque

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import audio
import auth
import db
import features
import instant
import interactions
import pipeline
import safety
from agents.common import EpisodeContext
from agents.showrunner import surprise_menu
from audit import read_audit, read_usage
from catalog import CURATED
from config import (AUDIO_DIR, DATA_MODE, EPISODE_BUDGET_USD, LENGTHS, MODEL_NAME, PRICES, RATE_LIMIT_EPISODES,
                    RATE_LIMIT_WINDOW_S, REPO, TTS_MODEL, TTS_USD_PER_1K_CHARS, has_api_key, openai_tts_key)
from models import AskRequest, ChoiceRequest, ConciergeAsk, EpisodeRequest, Feedback, InterviewAsk
from tokenomics import Ledger

app = FastAPI(title="Loremaster API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

_hits: dict[str, deque] = defaultdict(deque)


@app.on_event("startup")
async def _warm_voice() -> None:
    asyncio.get_running_loop().run_in_executor(None, audio.warm_up)  # load the voice model in the background


def rate_limit(request: Request, bucket: str = "episode", limit: int = RATE_LIMIT_EPISODES, what: str = "new episodes") -> None:
    """Overspend guard against a bad actor: at most N expensive actions per client per window, per bucket."""
    key = f"{bucket}:{request.client.host if request.client else 'local'}"
    q, now = _hits[key], time.time()
    while q and now - q[0] > RATE_LIMIT_WINDOW_S:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, f"Easy there, loremaster: max {limit} {what} per {RATE_LIMIT_WINDOW_S // 60} minutes.")
    q.append(now)


def stats_ok(request: Request) -> bool:
    """The listener can turn off the anonymous usage log in Settings; the browser then sends X-Usage-Stats: off."""
    return request.headers.get("x-usage-stats", "").lower() != "off"


def demo_only() -> bool:
    return DATA_MODE == "demo" or not has_api_key()


@app.get("/api/health")
def health():
    from config import provider
    return {"ok": True, "model": MODEL_NAME, "provider": provider(), "data_mode": DATA_MODE, "has_key": has_api_key(),
            "demo_only": demo_only(), "tts": bool(openai_tts_key()), "audio_engine": audio.engine(),
            "budget_usd": EPISODE_BUDGET_USD,
            "lengths": LENGTHS}


@app.get("/api/pricing")
def pricing():
    return {"model": MODEL_NAME, "prices_per_1m": PRICES[MODEL_NAME], "source": "Lecture 11 slides (OpenAI Standard tier)",
            "tts_model": TTS_MODEL, "tts_usd_per_1k_chars_estimate": TTS_USD_PER_1K_CHARS}


@app.get("/api/menu")
def menu():
    return {"threads": [t.model_dump() for t in CURATED]}


@app.get("/api/instant")
def instant_shelf():
    return {"stories": instant.shelf()}


@app.post("/api/menu/surprise")
async def surprise(request: Request, mode: str = "crossover"):
    if demo_only():
        raise HTTPException(400, "Surprise me needs a PORTKEY_API_KEY (Demo mode is on).")
    rate_limit(request)
    ectx = EpisodeContext(episode_id="menu", ledger=Ledger(budget_usd=0.01))
    threads = await surprise_menu(ectx, mode)
    return {"threads": [t.model_dump() for t in threads], "cost_usd": ectx.ledger.total_usd}


# ------------------------------------------------------------------ episodes
@app.post("/api/episode")
async def create_episode(req: EpisodeRequest, request: Request):
    if req.instant_id:  # pre-built: no key, no model calls, no wait
        if req.instant_id not in instant.load_all():
            raise HTTPException(404, "unknown instant story")
        run = await pipeline.start_instant(req.instant_id)
        return {"id": run.episode.id, "demo": False, "instant": True}
    if demo_only():
        ep = pipeline.demo_episode()
        if not ep:
            raise HTTPException(503, "Demo episode missing and no API key.")
        return {"id": "demo", "demo": True}
    rate_limit(request)
    try:
        run = pipeline.new_run(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    run.task = asyncio.create_task(pipeline.start(run, req))
    return {"id": run.episode.id, "demo": False}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


async def _demo_stream(chapters_shown: int):
    ep = pipeline.demo_episode()
    yield _sse({"type": "plan", "title": ep.title, "logline": ep.logline, "demo": True,
                "chapters": [c.model_dump() for c in ep.plan]})
    for ch in ep.chapters[:chapters_shown]:
        await asyncio.sleep(0.4)
        yield _sse({"type": "chapter_ready", "chapter": ch.model_dump()})
    status = "final" if chapters_shown >= len(ep.chapters) else "waiting_choice"
    if status == "final":
        yield _sse({"type": "final", "reading": [r.model_dump() for r in ep.reading]})
    else:
        yield _sse({"type": "waiting_choice", "options": ep.chapters[chapters_shown - 1].branch_options})
    ep.status = "done" if status == "final" else "waiting_choice"
    ep.chapters = ep.chapters[:chapters_shown]
    yield _sse({"type": "episode", "episode": ep.model_dump()})


_demo_progress: dict[str, int] = defaultdict(lambda: 1)


@app.get("/api/episode/{eid}/stream")
async def stream(eid: str, request: Request):
    if eid == "demo":
        key = request.client.host if request.client else "local"
        return StreamingResponse(_demo_stream(_demo_progress[key]), media_type="text/event-stream")
    run = pipeline.RUNS.get(eid)
    if not run:
        saved = db.load_episode(eid)
        if not saved:
            raise HTTPException(404, "no such episode")
        run = pipeline.resume_run(saved)
    queue: asyncio.Queue = asyncio.Queue()
    past = list(run.events)
    run.subscribers.append(queue)

    async def gen():
        try:
            for ev in past:
                yield _sse(ev)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _sse(ev)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if queue in run.subscribers:
                run.subscribers.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/episode/{eid}")
def get_episode(eid: str):
    if eid == "demo":
        return pipeline.demo_episode().model_dump()
    run = pipeline.RUNS.get(eid)
    ep = run.episode if run else db.load_episode(eid)
    if not ep:
        raise HTTPException(404, "no such episode")
    return ep.model_dump()


@app.post("/api/episode/{eid}/choose")
async def choose(eid: str, body: ChoiceRequest, request: Request):
    if eid == "demo":
        key = request.client.host if request.client else "local"
        _demo_progress[key] = min(_demo_progress[key] + 1, len(pipeline.demo_episode().chapters))
        return {"ok": True}
    run = pipeline.RUNS.get(eid)
    if not run:
        saved = db.load_episode(eid)
        if not saved or saved.status != "waiting_choice":
            raise HTTPException(404, "episode not found or already finished")
        if demo_only():
            raise HTTPException(400, "Continuing an episode needs a PORTKEY_API_KEY.")
        run = pipeline.resume_run(saved)
    if run.episode.status not in ("waiting_choice", "stopped") or not run.episode.chapters:
        raise HTTPException(409, f"episode is {run.episode.status}")
    if run.task and not run.task.done():
        raise HTTPException(409, "still working on the last chapter")
    if run.instant_id and await pipeline.choose_instant(run, body.branch):
        return {"ok": True, "instant": True}
    run.task = asyncio.create_task(pipeline.choose(run, body.branch))
    return {"ok": True}


_qa: dict[str, str] = {}   # answer id -> spoken text (for its audio)


@app.post("/api/episode/{eid}/ask")
async def ask(eid: str, body: AskRequest, request: Request):
    """Ask the narrator: a short, graded, sourced answer about the current chapter."""
    from agents import answerer, guardian
    run = pipeline.RUNS.get(eid)
    if not run:
        saved = db.load_episode(eid)
        if not saved:
            raise HTTPException(404, "no such episode")
        run = pipeline.resume_run(saved)
    if demo_only():
        raise HTTPException(400, "Asking the narrator needs a PORTKEY_API_KEY.")
    ep = run.episode
    asked = sum(1 for e in run.events if e.get("type") == "answer")
    if asked >= 8:
        raise HTTPException(429, "That's 8 questions for this episode. Keep listening!")
    ch = next((c for c in ep.chapters if c.index == body.chapter), ep.chapters[-1] if ep.chapters else None)
    if not ch:
        raise HTTPException(409, "No chapter yet.")
    verdict = guardian.code_check(body.question)  # free regex gate (injection, denial, partisan, length)
    if verdict:
        return {"refused": True, "reason": verdict.reason}
    try:
        draft, cards = await answerer.answer(run.ectx, ep.thread, ch, body.question)
    except Exception as e:
        raise HTTPException(502, f"The narrator couldn't answer right now ({type(e).__name__}). Try again.")
    import uuid as _u
    qid = _u.uuid4().hex[:10]
    # spoken text: no claim tags, and no [bracketed asides] read out as brackets
    answer = re.sub(r"\[([^\[\]]+)\]", r"\1", re.sub(r"\s*\[c\d+\]", "", draft.answer)).strip()
    _qa[qid] = answer
    asyncio.create_task(audio.render_whole(answer))   # warm the default voice while the listener reads
    out = {"id": qid, "question": body.question, "answer": answer, "on_topic": draft.on_topic,
           "claims": [{**c.model_dump(), "evidence": [cards[e].model_dump() for e in c.evidence_ids if e in cards]} for c in draft.claims],
           "cost_usd": round(run.ectx.ledger.total_usd, 6)}
    await run.emit({"type": "answer", "chapter": ch.index, **out})
    if stats_ok(request):
        interactions.log(interactions.Interaction(kind="ask", episode_id=eid, chapter=ch.index, data={"question": body.question[:200]}))
    return out


@app.get("/api/answer/{qid}/audio")
async def answer_audio(qid: str, voice: str = audio.DEFAULT_VOICE):
    text = _qa.get(qid)
    if not text:
        raise HTTPException(404, "unknown answer")
    path = await audio.render_whole(text, voice)
    if not path:
        raise HTTPException(404, "No audio engine.")
    return FileResponse(path, media_type=audio.MEDIA[path.suffix])


# ------------------------------------------------------------------ Snap & Story · Interview the past · Concierge
from pydantic import BaseModel as _BM


class SnapBody(_BM):
    image_b64: str
    media_type: str = "image/jpeg"


@app.post("/api/snap")
async def snap(body: SnapBody, request: Request):
    if demo_only():
        raise HTTPException(400, "Snap & Story needs an API key.")
    rate_limit(request, bucket="snap", limit=12, what="photos")   # ~$0.0004 each, so its own, roomier bucket
    try:
        out = await features.snap(body.image_b64, body.media_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if stats_ok(request):
        interactions.log(interactions.Interaction(kind="snap", data={"what": out["id"]["what"][:80], "allowed": out["allowed"]}))
    return out


@app.get("/api/interview/characters")
def interview_characters():
    return {"characters": features.CHARACTERS}


class InterviewStartBody(_BM):
    character_id: str | None = None
    custom_name: str | None = None


@app.post("/api/interview/start")
async def interview_start(body: InterviewStartBody, request: Request):
    if demo_only():
        raise HTTPException(400, "Interviews need an API key.")
    try:
        return await features.start_interview(body.character_id, body.custom_name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/interview/{sid}/ask")
async def interview_ask(sid: str, body: InterviewAsk, request: Request):
    rate_limit(request, bucket="chat", limit=40, what="questions")
    try:
        out = await features.ask_interview(sid, body.question)
    except KeyError:
        raise HTTPException(404, "That interview has ended. Start a new one.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not out.get("refused"):
        import uuid as _u
        qid = _u.uuid4().hex[:10]
        _qa[qid] = out["answer"]
        out["id"] = qid
        if stats_ok(request):
            interactions.log(interactions.Interaction(kind="interview", data={"character": features.INTERVIEWS[sid].char["name"]}))
    return out


@app.post("/api/concierge")
async def concierge(body: ConciergeAsk, request: Request):
    if demo_only():
        raise HTTPException(400, "The concierge needs an API key.")
    rate_limit(request, bucket="chat", limit=40, what="questions")
    out = await features.concierge(body.message)
    if stats_ok(request):
        interactions.log(interactions.Interaction(kind="concierge", data={"message": body.message[:120]}))
    return out


@app.post("/api/events")
def log_event(ev: interactions.Interaction, request: Request):
    user = auth.user_for(_bearer(request)) if "_bearer" in globals() else None
    interactions.log(ev, user["id"] if user else None)
    return {"ok": True}


@app.get("/api/events/summary")
def events_summary():
    return interactions.summary()


@app.post("/api/episode/{eid}/cancel")
def cancel(eid: str):
    """Stop button: cancel the running task. The in-flight model call is abandoned and no further calls start."""
    run = pipeline.RUNS.get(eid)
    if not run:
        return {"ok": True, "stopped": False}
    run.ectx.cancelled = True
    stopped = bool(run.task and not run.task.done())
    if stopped:
        run.task.cancel()
    return {"ok": True, "stopped": stopped}


@app.post("/api/demo/reset")
def demo_reset(request: Request):
    key = request.client.host if request.client else "local"
    _demo_progress[key] = 1
    return {"ok": True}


# ------------------------------------------------------------------ library, audit, usage
@app.get("/api/library")
def library():
    return {"episodes": db.list_episodes()}


@app.get("/api/audit/{eid}")
def audit_for(eid: str):
    return {"entries": read_audit(eid)}


@app.get("/api/usage/latest")
def usage_latest(limit: int = 30):
    return {"runs": read_usage(limit)}


# ------------------------------------------------------------------ safety lab
@app.get("/api/safety/demos")
def safety_demos():
    return {"demos": safety.DEMOS}


@app.post("/api/safety/run/{demo}")
async def safety_run(demo: str, defenses: str = "all"):
    if demo not in safety.RUNNERS:
        raise HTTPException(404, "unknown demo")
    if demo_only():
        raise HTTPException(400, "The Safety Lab needs a PORTKEY_API_KEY. Recorded results: output/safety_results.md")
    return await safety.run_demo(demo, defenses)


# ------------------------------------------------------------------ feedback & blind test
@app.post("/api/feedback")
def feedback(f: Feedback):
    return {"id": db.save_feedback(f)}


@app.get("/api/feedback")
def feedback_list():
    return {"feedback": db.list_feedback()}


@app.post("/api/blind_test")
async def blind_test(request: Request):
    payload = await request.json()
    return {"id": db.save_blind_test(str(payload.get("tester", ""))[:80], payload)}


# ------------------------------------------------------------------ narration audio (real files; see audio.py)
def _episode_for_audio(eid: str):
    if eid == "demo":
        return pipeline.demo_episode()
    if eid in pipeline.RUNS:
        return pipeline.RUNS[eid].episode
    return db.load_episode(eid)


@app.get("/api/audio/{eid}/{chapter}/manifest")
async def audio_manifest(eid: str, chapter: int, voice: str = audio.DEFAULT_VOICE):
    ep = _episode_for_audio(eid)
    ch = next((c for c in (ep.chapters if ep else []) if c.index == chapter), None)
    if not ch:
        raise HTTPException(404, "no such chapter")
    segs = audio.segment_map(ch.narration)
    if audio.engine() != "none":
        asyncio.create_task(audio.prerender(eid, chapter, ch.narration, voice))  # warm the rest while #0 plays
    return {"engine": audio.engine(), "voice": voice,
            "segments": [{"index": i, "chars": len(t), "paras": paras} for i, (t, paras) in enumerate(segs)]}


@app.get("/api/audio/{eid}/{chapter}/{seg}")
async def audio_segment(eid: str, chapter: int, seg: int, voice: str = audio.DEFAULT_VOICE):
    ep = _episode_for_audio(eid)
    ch = next((c for c in (ep.chapters if ep else []) if c.index == chapter), None)
    if not ch:
        raise HTTPException(404, "no such chapter")
    path = await audio.render_segment(eid, chapter, seg, ch.narration, voice)
    if not path:
        raise HTTPException(404, "No audio engine on this computer: the app uses your browser's voice instead.")
    return FileResponse(path, media_type=audio.MEDIA[path.suffix], headers={"Cache-Control": "max-age=86400"})


# ------------------------------------------------------------------ accounts & preferences
_login_hits: dict[str, deque] = defaultdict(deque)


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:] if h.lower().startswith("bearer ") else None


def _throttle_login(request: Request) -> None:
    key = request.client.host if request.client else "local"
    q, now = _login_hits[key], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 8:
        raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
    q.append(now)


@app.get("/api/auth/challenge")
def auth_challenge():
    return {"challenge": auth.new_challenge(), "min_seconds": auth.CHALLENGE_MIN_S}


@app.post("/api/auth/signup")
def signup(body: auth.SignUp, request: Request):
    _throttle_login(request)
    try:
        token, user = auth.sign_up(body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"token": token, "user": user}


@app.post("/api/auth/login")
def login(body: auth.LogIn, request: Request):
    _throttle_login(request)
    try:
        token, user = auth.log_in(body)
    except ValueError as e:
        raise HTTPException(401, str(e))
    return {"token": token, "user": user}


@app.post("/api/auth/logout")
def logout(request: Request):
    if t := _bearer(request):
        auth.log_out(t)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    user = auth.user_for(_bearer(request))
    if not user:
        raise HTTPException(401, "Not logged in.")
    return {"user": user}


@app.put("/api/me/prefs")
def update_prefs(prefs: auth.Prefs, request: Request):
    user = auth.user_for(_bearer(request))
    if not user:
        raise HTTPException(401, "Not logged in.")
    return {"user": auth.save_prefs(user["id"], prefs)}


def _me(request: Request) -> tuple[dict, str]:
    token = _bearer(request)
    user = auth.user_for(token)
    if not user:
        raise HTTPException(401, "Not logged in.")
    return user, token


@app.post("/api/me/password")
def change_password(body: auth.PasswordChange, request: Request):
    _throttle_login(request)
    user, token = _me(request)
    try:
        auth.change_password(user["id"], token, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.put("/api/me/name")
def change_name(body: auth.NameChange, request: Request):
    user, _ = _me(request)
    return {"user": auth.rename(user["id"], body.name)}


@app.post("/api/me/logout-others")
def logout_others(request: Request):
    user, token = _me(request)
    return {"ended": auth.log_out_everywhere(user["id"], token)}


@app.post("/api/me/delete")
def delete_me(body: auth.Confirm, request: Request):
    _throttle_login(request)
    user, _ = _me(request)
    try:
        auth.delete_account(user["id"], body.password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


VOICE_SAMPLE = ("Constantinople, the twenty-ninth of May, fourteen fifty-three. The great chain across the Golden Horn is "
                "useless now. Ten thousand years from now, on Terra, the Custodes will hold another wall.")


@app.get("/api/voice-sample/{voice}")
async def voice_sample(voice: str):
    path = await audio.render_segment("sample", 0, 0, VOICE_SAMPLE, voice)
    if not path:
        raise HTTPException(404, "No audio engine on this computer.")
    return FileResponse(path, media_type=audio.MEDIA[path.suffix], headers={"Cache-Control": "max-age=86400"})


@app.get("/api/voices")
def voice_list():
    return {"engine": audio.engine(), "voices": audio.voices(), "default": audio.DEFAULT_VOICE}


# ------------------------------------------------------------------ built frontend (optional single-server mode)
_dist = REPO / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
