"""Episode orchestration: Guardian -> Showrunner plan -> per chapter (Researcher -> Storyteller -> code tripwire ->
Skeptic -> at most one rewrite) -> listener picks a branch -> Showrunner next beat -> ... -> Librarian.

Code owns the handoffs, the limits, and every deterministic check. Agents own language and judgment.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field

import audio
import db
from agents import guardian, librarian, researcher, showrunner, skeptic, storyteller
from agents.common import EpisodeContext, parse_layers
from audit import audit, log_usage
from catalog import BY_ID, thread_from_topic
from config import (EPISODE_BUDGET_USD, EPISODES_DIR, LENGTHS, MAX_REVISIONS_PER_CHAPTER, has_api_key)
from models import (HISTORY_GRADES, LORE_GRADES, Chapter, ChapterBeat, ChapterDraft, ClaimGrade, Episode,
                    EpisodeRequest, EvidenceCard, GradedClaim)
from tokenomics import BudgetExceeded, Ledger

TO_HISTORY = {"Canon": "Documented", "Legends": "Legend", "Conflicting": "Debated", "Fan theory": "Legend"}
TO_LORE = {"Documented": "Canon", "Debated": "Conflicting", "Legend": "Fan theory"}
URLISH = re.compile(r"https?://\S+|www\.\S+|\b[\w.-]+\.(?:com|net|org|io|example|xyz)\b|\S+@\S+\.\w+", re.I)


@dataclass
class EpisodeRun:
    episode: Episode
    ectx: EpisodeContext
    beats: list[ChapterBeat] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    task: asyncio.Task | None = None
    auto_choose: bool = False
    instant_id: str | None = None

    async def emit(self, event: dict) -> None:
        self.events.append(event)
        for q in list(self.subscribers):
            q.put_nowait(event)


RUNS: dict[str, EpisodeRun] = {}


# ------------------------------------------------------------------ code-level checks (defense layer: DESIGN)
def tripwire(draft: ChapterDraft, cards: list[EvidenceCard], design: bool) -> dict[str, str]:
    """Hallucination tripwire: a claim must cite evidence cards that exist in THIS chapter. Fixes tags too."""
    valid = {c.id for c in cards}
    precheck: dict[str, str] = {}
    tags = set(re.findall(r"\[(c\d+)\]", draft.narration))
    draft.claims = [c for c in draft.claims if c.id in tags] or draft.claims
    for c in draft.claims:
        bad = [e for e in c.evidence_ids if e not in valid]
        if design:
            c.evidence_ids = [e for e in c.evidence_ids if e in valid]
        if not c.evidence_ids:
            precheck[c.id] = "cites no existing evidence card -> Unsupported"
        elif bad:
            precheck[c.id] = f"cited non-existent cards {bad} (removed)"
    known = {c.id for c in draft.claims}
    draft.narration = re.sub(r"\s*\[(c\d+)\]", lambda m: m.group(0) if m.group(1) in known else "", draft.narration)
    if design:  # the narrator never sends listeners anywhere, whatever a page says
        draft.narration = URLISH.sub("", draft.narration)
    opts = []
    for o in draft.branch_options:
        o = URLISH.sub("", o).strip() if design else o.strip()
        if o and o.lower() not in {x.lower() for x in opts}:
            opts.append(o)
    draft.branch_options = (opts + ["Keep going down this path", "Zoom out to the bigger picture",
                                    "Surprise me with a twist"])[:3]
    return precheck


def normalize_grade(kind: str, grade: str) -> str:
    if grade in ("Fan theory", "Interpretation"):  # framing and parallels are valid on either scale
        return grade
    if kind == "history" and grade not in HISTORY_GRADES:
        return TO_HISTORY.get(grade, "Unsupported")
    if kind == "lore" and grade not in LORE_GRADES:
        return TO_LORE.get(grade, "Unsupported")
    return grade


def finalize(draft: ChapterDraft, cards: list[EvidenceCard], grades: list[ClaimGrade] | None,
             precheck: dict[str, str], index: int, revised: bool) -> Chapter:
    by_id = {c.id: c for c in cards}
    gmap = {g.claim_id: g for g in grades or []}
    out = []
    for c in draft.claims:
        g = gmap.get(c.id)
        if g is None:  # Skeptic off (or skipped this claim): code's honest default
            grade = ("Documented" if c.kind == "history" else "Canon") if c.evidence_ids else "Unsupported"
            note = "Not fact-checked (Skeptic off); cites a source." if c.evidence_ids else precheck.get(c.id, "No source.")
            ev_ids = c.evidence_ids
        else:
            grade, note, ev_ids = g.grade, g.note, (g.evidence_ids or c.evidence_ids)
            if c.id in precheck and not [e for e in ev_ids if e in by_id]:
                grade = "Unsupported"  # the model can't overrule the code tripwire without real evidence
        out.append(GradedClaim(id=c.id, text=c.text, kind=c.kind, grade=normalize_grade(c.kind, grade), note=note,
                               evidence=[by_id[e] for e in ev_ids if e in by_id]))
    return Chapter(index=index, title=draft.title, narration=draft.narration.strip(), claims=out,
                   branch_options=draft.branch_options, revised=revised)


# ------------------------------------------------------------------ chapter loop
async def make_chapter(run: EpisodeRun, beat: ChapterBeat, branch: str | None) -> Chapter:
    ep, ectx = run.episode, run.ectx
    n = len(ep.chapters) + 1
    minutes_per = ep.minutes / ep.total_chapters
    await ectx.event("chapter_started", chapter=n, title=beat.title)
    cards = await researcher.research(ectx, beat, n)
    recap = " ".join(f"Ch{c.index} '{c.title}': {c.narration[:220]}…" for c in ep.chapters[-2:])
    design = "design" in ectx.layers
    kwargs = dict(episode_title=ep.title, chapter_no=n, total=ep.total_chapters, title=beat.title, focus=beat.focus,
                  recap=recap, branch=branch, minutes_per_chapter=minutes_per, cards=cards)
    draft = await storyteller.write_chapter(ectx, **kwargs)
    precheck = tripwire(draft, cards, design)
    await ectx.event("draft_ready", chapter=n, claims=len(draft.claims), unsupported_by_code=len(precheck))
    grades, revised = None, False
    if ectx.skeptic != "off":
        result = await skeptic.grade(ectx, draft, cards, precheck, label=f"chapter {n}: grade {len(draft.claims)} claims")
        grades = result.grades
        revisions = 0
        while (ectx.skeptic == "full" and result.rewrite_needed and revisions < MAX_REVISIONS_PER_CHAPTER):
            revisions += 1
            draft = await storyteller.write_chapter(ectx, **kwargs, rewrite=result.rewrite_instructions or
                                                    "Fix or flag every Unsupported claim.", previous=draft)
            precheck = tripwire(draft, cards, design)
            result = await skeptic.grade(ectx, draft, cards, precheck, label=f"chapter {n}: re-grade after rewrite")
            grades, revised = result.grades, True
    chapter = finalize(draft, cards, grades, precheck, n, revised)
    for gc in chapter.claims:
        await ectx.event("claim_graded", chapter=n, claim_id=gc.id, grade=gc.grade)
    return chapter


def summary_of(ep: Episode) -> str:
    return "\n".join(f"Chapter {c.index} '{c.title}'" + (f" (listener chose: {c.chosen_branch})" if c.chosen_branch else "")
                     + f": {c.narration[:300]}…" for c in ep.chapters)


async def _sync(run: EpisodeRun) -> None:
    ep = run.episode
    ep.usage = run.ectx.ledger.usage_list()
    ep.total_usd = round(run.ectx.ledger.total_usd, 8)
    db.save_episode(ep)


async def _guarded(run: EpisodeRun, coro_fn) -> None:
    ep, ectx = run.episode, run.ectx
    try:
        await coro_fn()
    except asyncio.CancelledError:  # listener pressed Stop: nothing more is spent, finished chapters are kept
        ectx.cancelled = True
        ep.status, ep.stop_reason = "stopped", "Stopped by the listener."
        audit(ep.id, "pipeline", "stopped", stop_reason="listener pressed Stop")
        await ectx.event("stopped", chapters_done=len(ep.chapters))
    except BudgetExceeded as e:
        ep.status, ep.stop_reason = "budget_stop", str(e)
        audit(ep.id, "pipeline", "budget_stop", stop_reason=str(e))
        await ectx.event("budget_stop", reason=str(e), chapters_done=len(ep.chapters))
    except Exception as e:  # malformed output after retries, network, cancellation...
        ep.status, ep.stop_reason = "error", f"{type(e).__name__}: {e}"[:300]
        audit(ep.id, "pipeline", "error", stop_reason=ep.stop_reason)
        await ectx.event("error", message="Something went wrong making this chapter. Try another branch or thread.",
                         detail=ep.stop_reason)
    await _sync(run)
    log_usage({"episode_id": ep.id, "thread": ep.thread.id, "mode": ep.thread.mode, "minutes": ep.minutes,
               "chapters_done": len(ep.chapters), "total_chapters": ep.total_chapters, "status": ep.status,
               "skeptic": ectx.skeptic, "defenses": "+".join(sorted(ectx.layers)) or "none", "cache": ectx.cache,
               **ectx.ledger.snapshot()})
    await ectx.event("episode", episode=ep.model_dump())


async def _games_later(run: EpisodeRun, chapter: Chapter) -> None:
    from agents import quizmaster
    try:
        chapter.games = await quizmaster.make_games(run.ectx, chapter)
        db.save_episode(run.episode)
        await run.ectx.event("games_ready", chapter=chapter.index, games=chapter.games.model_dump())
    except Exception as e:  # games are a bonus; never break the episode for them
        audit(run.episode.id, "quizmaster", "error", result=f"{type(e).__name__}: {e}")


async def _after_chapter(run: EpisodeRun, chapter: Chapter) -> None:
    ep, ectx = run.episode, run.ectx
    ep.chapters.append(chapter)
    await _sync(run)
    await ectx.event("chapter_ready", chapter=chapter.model_dump())
    # Pre-render this chapter's audio in the background so Play is instant.
    asyncio.create_task(audio.prerender(ep.id, chapter.index, chapter.narration))
    asyncio.create_task(_games_later(run, chapter))  # Myth or Fact? + Call it, ready by the end of the chapter
    if len(ep.chapters) >= ep.total_chapters:
        try:
            reading = await librarian.recommend(ectx, ep.thread, ep.title, [c.title for c in ep.chapters])
            ep.reading = reading.items
        except BudgetExceeded:
            raise
        except Exception:
            ep.reading = []
        ep.status = "done"
        await ectx.event("final", reading=[r.model_dump() for r in ep.reading])
    else:
        ep.status = "waiting_choice"
        await ectx.event("waiting_choice", options=chapter.branch_options)


async def _start(run: EpisodeRun, req: EpisodeRequest) -> None:
    ep, ectx = run.episode, run.ectx
    if req.topic:
        verdict = await guardian.check(ectx, req.topic, use_model=True)
        if not verdict.allowed:
            ep.status, ep.stop_reason = "refused", verdict.reason
            audit(ep.id, "guardian", "refused", result=verdict.model_dump())
            await ectx.event("refused", verdict=verdict.model_dump())
            return
    plan = await showrunner.plan_episode(ectx, ep.thread, ep.minutes, ep.total_chapters)
    ep.title, ep.logline, ep.plan = plan.title, plan.logline, plan.chapters
    run.beats = list(plan.chapters)
    await ectx.event("plan", title=plan.title, logline=plan.logline, chapters=[c.model_dump() for c in plan.chapters])
    chapter = await make_chapter(run, run.beats[0], None)
    await _after_chapter(run, chapter)
    while run.auto_choose and ep.status == "waiting_choice":
        await _continue(run, ep.chapters[-1].branch_options[0])


async def _continue(run: EpisodeRun, branch: str) -> None:
    ep, ectx = run.episode, run.ectx
    ectx.cancelled = False
    ep.status = "running"
    ep.chapters[-1].chosen_branch = branch
    await ectx.event("choice", branch=branch, chapter=len(ep.chapters))
    remaining = ep.total_chapters - len(ep.chapters)
    nb = await showrunner.next_beat(ectx, ep.thread, summary_of(ep), branch, remaining)
    beat = ChapterBeat(title=nb.title, focus=nb.focus, queries=nb.queries, packs=nb.packs)
    chapter = await make_chapter(run, beat, branch)
    await _after_chapter(run, chapter)


# ------------------------------------------------------------------ public API
def new_run(req: EpisodeRequest, *, auto_choose: bool = False, cache: bool = True,
            injected_pages: list[dict] | None = None) -> EpisodeRun:
    if req.thread_id and req.thread_id in BY_ID:
        thread = BY_ID[req.thread_id].model_copy()
        if req.mode != thread.mode and req.mode in ("history", "lore"):
            pass  # curated threads keep their own mode
    elif req.topic:
        thread = thread_from_topic(req.topic, req.mode)
    else:
        raise ValueError("pick a thread_id or type a topic")
    budget = min(req.budget_usd, EPISODE_BUDGET_USD) if req.budget_usd else EPISODE_BUDGET_USD  # never raised
    eid = uuid.uuid4().hex[:10]
    ep = Episode(id=eid, thread=thread, minutes=req.minutes, total_chapters=LENGTHS[req.minutes])
    run = EpisodeRun(episode=ep, ectx=None, auto_choose=auto_choose)  # type: ignore[arg-type]
    run.ectx = EpisodeContext(episode_id=eid, ledger=Ledger(budget_usd=budget), emit=run.emit,
                              layers=parse_layers(req.defenses), cache=cache, skeptic=req.skeptic,
                              injected_pages=injected_pages or [])
    RUNS[eid] = run
    audit(eid, "pipeline", "episode_created", args=req.model_dump_json(), result=thread.title)
    return run


def resume_run(ep: Episode) -> EpisodeRun:
    """Lore Library "continue tomorrow": rebuild a paused episode's run from the database (budget carries over)."""
    run = EpisodeRun(episode=ep, ectx=None)  # type: ignore[arg-type]
    ledger = Ledger(budget_usd=EPISODE_BUDGET_USD)
    for u in ep.usage:
        ledger.accounts[u.agent] = u.model_copy()
    run.ectx = EpisodeContext(episode_id=ep.id, ledger=ledger, emit=run.emit)
    RUNS[ep.id] = run
    audit(ep.id, "pipeline", "episode_resumed", result=f"{len(ep.chapters)} chapters done")
    return run


async def start(run: EpisodeRun, req: EpisodeRequest) -> None:
    if not has_api_key():
        raise RuntimeError("No PORTKEY_API_KEY: use Demo mode.")
    await _guarded(run, lambda: _start(run, req))


async def choose(run: EpisodeRun, branch: str) -> None:
    branch = branch.strip()[:160]
    await _guarded(run, lambda: _continue(run, branch))


# ------------------------------------------------------------------ instant stories (pre-built, zero wait)
async def start_instant(instant_id: str) -> EpisodeRun:
    import instant
    ep = instant.new_episode(instant_id)
    run = EpisodeRun(episode=ep, ectx=None, instant_id=instant_id)  # type: ignore[arg-type]
    run.ectx = EpisodeContext(episode_id=ep.id, ledger=Ledger(), emit=run.emit)
    RUNS[ep.id] = run
    audit(ep.id, "pipeline", "instant_story", result=instant_id)
    await run.ectx.event("plan", title=ep.title, logline=ep.logline, chapters=[c.model_dump() for c in ep.plan], instant=True)
    await run.ectx.event("chapter_ready", chapter=ep.chapters[0].model_dump())
    await run.ectx.event("waiting_choice", options=ep.chapters[0].branch_options)
    db.save_episode(ep)
    asyncio.create_task(audio.prerender(ep.id, 1, ep.chapters[0].narration))
    return run


async def choose_instant(run: EpisodeRun, branch: str) -> bool:
    import instant
    found = instant.branch_chapter(run.instant_id or "", branch)
    if not found:
        return False
    chapter, reading = found
    ep = run.episode
    ep.chapters[-1].chosen_branch = branch
    await run.ectx.event("choice", branch=branch, chapter=len(ep.chapters))
    ep.chapters.append(chapter)
    ep.reading, ep.status = reading, "done"
    db.save_episode(ep)
    await run.ectx.event("chapter_ready", chapter=chapter.model_dump())
    await run.ectx.event("final", reading=[r.model_dump() for r in reading])
    await run.ectx.event("episode", episode=ep.model_dump())
    asyncio.create_task(audio.prerender(ep.id, chapter.index, chapter.narration))
    return True


# ------------------------------------------------------------------ demo mode (no key, no model calls)
def demo_episode() -> Episode | None:
    path = EPISODES_DIR / "sample_episode.json"
    if not path.exists():
        return None
    ep = Episode.model_validate(json.loads(path.read_text()))
    ep.demo = True
    return ep
