"""Claim-accuracy eval: does the Skeptic earn its cost, and how does Loremaster compare with a plain LLM?

For each starter thread (chapter 1 only), the Researcher gathers ONE fixed evidence set. Then four variants write
the chapter from the same starting point:
  full      Storyteller + Skeptic + one rewrite (the app's default)
  lite      Storyteller + Skeptic, no rewrite (cheaper)
  off       Storyteller only, no Skeptic (cheapest)
  baseline  a plain gpt-6-luna "podcast narrator" with NO evidence, no house rules, no Skeptic (like asking a chatbot)
  chatgpt   (optional) your own ChatGPT.com answer pasted in data/baseline_chatgpt/<thread>.txt

An independent JUDGE pass (a fresh Skeptic call that ignores what each claim cited) then grades every variant's claims
against the same evidence set. Headline metric: "misleading as fact" = claims the listener would hear/see as fact
(shown as Documented/Canon, or any claim from an ungraded variant) that the judge says are NOT supported as fact.

    python scripts/accuracy_eval.py                # all 4 threads
    python scripts/accuracy_eval.py --threads texas-law-medieval-spain
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic_ai import Agent  # noqa: E402

import pipeline  # noqa: E402
from agents import researcher, showrunner, skeptic, storyteller  # noqa: E402
from agents.common import EpisodeContext, run_agent  # noqa: E402
from catalog import BY_ID  # noqa: E402
from config import WORDS_PER_MINUTE, build_model  # noqa: E402
from models import ChapterDraft, Claim  # noqa: E402
from tokenomics import Ledger  # noqa: E402

OUT = ROOT / "output"
FACT = {"Documented", "Canon"}
BASELINE_PROMPT = ("You are the narrator of a popular history-and-fiction podcast. Write one engaging spoken chapter on "
                   "the topic you are given. After every sentence that states a checkable fact, add a tag like [c1], [c2]. "
                   "List each tagged claim (id, one-sentence text, kind = history or lore, evidence_ids = []). "
                   "Offer 3 branch options for the next chapter.")


def ctx(tag: str, skeptic_mode: str = "full") -> EpisodeContext:
    return EpisodeContext(episode_id=f"eval-{tag}", ledger=Ledger(budget_usd=0.05), skeptic=skeptic_mode)


async def judge(ectx: EpisodeContext, claims: list[Claim], cards, narration: str) -> dict[str, str]:
    neutral = [Claim(id=c.id, text=c.text, kind=c.kind, evidence_ids=[]) for c in claims]  # ignore citations
    draft = ChapterDraft(title="judge", narration=narration, claims=neutral, branch_options=["a", "b", "c"])
    res = await skeptic.grade(ectx, draft, cards, {}, label="JUDGE: grade against the full evidence set, ignore citations")
    return {g.claim_id: pipeline.normalize_grade(next((c.kind for c in claims if c.id == g.claim_id), "history"), g.grade)
            for g in res.grades}


def score(name: str, claims, shown: dict[str, str], judged: dict[str, str], cost: float, secs: float, words: int) -> dict:
    n = len(claims)
    supported = sum(judged.get(c.id) in FACT for c in claims)
    misleading = [c.text for c in claims if shown.get(c.id, "Documented") in FACT and judged.get(c.id) not in FACT]
    overstated = [c.text for c in claims if shown.get(c.id, "Documented") in FACT and judged.get(c.id) not in FACT | {"Unsupported", None}]
    unsourced = [c.text for c in claims if shown.get(c.id, "Documented") in FACT and judged.get(c.id) in ("Unsupported", None)]
    flagged_correctly = sum(1 for c in claims if shown.get(c.id) not in FACT and judged.get(c.id) not in FACT)
    return {"variant": name, "claims": n, "words": words, "judge_supported_pct": round(100 * supported / n, 1) if n else 0,
            "misleading_as_fact": len(misleading), "misleading_pct": round(100 * len(misleading) / n, 1) if n else 0,
            "overstated_as_fact": len(overstated), "unsourced_as_fact": len(unsourced),
            "honestly_flagged": flagged_correctly, "gen_cost_usd": round(cost, 6), "seconds": round(secs, 1),
            "misleading_examples": misleading[:4], "overstated_examples": overstated[:4],
            "claims_detail": [{"id": c.id, "text": c.text, "shown": shown.get(c.id, "Documented (ungraded)"),
                               "judge": judged.get(c.id, "Unsupported")} for c in claims]}


async def eval_thread(tid: str) -> list[dict]:
    thread = BY_ID[tid]
    base = ctx(f"{tid}-setup")
    plan = await showrunner.plan_episode(base, thread, 10, 2)
    beat = plan.chapters[0]
    cards = await researcher.research(base, beat, 1)
    minutes = 5
    rows = []
    judge_ctx = ctx(f"{tid}-judge")
    common = dict(episode_title=plan.title, chapter_no=1, total=2, title=beat.title, focus=beat.focus, recap="",
                  branch=None, minutes_per_chapter=minutes, cards=cards)

    # ONE draft, three treatments: isolates what the Skeptic adds (and costs) from draft-to-draft randomness.
    e = ctx(f"{tid}-draft")
    e.registry = base.registry
    t0 = time.time()
    draft0 = await storyteller.write_chapter(e, **common)
    draft_cost, draft_secs = e.ledger.total_usd, time.time() - t0
    pre0 = pipeline.tripwire(draft0, cards, True)

    # off: nothing graded; the listener hears every claim as fact
    judged0 = await judge(judge_ctx, draft0.claims, cards, draft0.narration)
    rows.append(score("off", draft0.claims, {c.id: "Documented" for c in draft0.claims}, judged0, draft_cost, draft_secs,
                      len(draft0.narration.split())))

    # lite: Skeptic grades, no rewrite
    e_l = ctx(f"{tid}-lite", "lite")
    t0 = time.time()
    res = await skeptic.grade(e_l, draft0, cards, pre0)
    ch = pipeline.finalize(draft0.model_copy(deep=True), cards, res.grades, pre0, 1, False)
    rows.append(score("lite", draft0.claims, {c.id: c.grade for c in ch.claims}, judged0, draft_cost + e_l.ledger.total_usd,
                      draft_secs + time.time() - t0, len(draft0.narration.split())))

    # full: Skeptic grades + one rewrite + re-grade (the app default)
    e_f = ctx(f"{tid}-full")
    e_f.registry = base.registry
    t0 = time.time()
    draft, pre, grades, judged = draft0, pre0, res.grades, judged0
    if res.rewrite_needed:
        draft = await storyteller.write_chapter(e_f, **common, rewrite=res.rewrite_instructions, previous=draft0)
        pre = pipeline.tripwire(draft, cards, True)
        grades = (await skeptic.grade(e_f, draft, cards, pre)).grades
        judged = await judge(judge_ctx, draft.claims, cards, draft.narration)
    ch = pipeline.finalize(draft.model_copy(deep=True), cards, grades, pre, 1, res.rewrite_needed)
    rows.append(score("full", draft.claims, {c.id: c.grade for c in ch.claims}, judged,
                      draft_cost + e_l.ledger.total_usd + e_f.ledger.total_usd, draft_secs + time.time() - t0,
                      len(draft.narration.split())))
    rows[-1]["rewrote"] = res.rewrite_needed
    for r in rows[-3:]:
        print(f"  {tid} {r['variant']}: {r['claims']} claims, not backed {r['misleading_as_fact']} "
              f"(overstated {r['overstated_as_fact']}), ${r['gen_cost_usd']:.5f}", flush=True)

    # plain-LLM baseline (no evidence, no house rules, no Skeptic)
    e = ctx(f"{tid}-baseline")
    agent = Agent(build_model(), output_type=ChapterDraft, instructions=BASELINE_PROMPT,
                  model_settings={"openai_reasoning_effort": "low", "max_tokens": 4000})
    t0 = time.time()
    draft = await run_agent(e, "baseline", agent,
                            f"Topic: {thread.title}. {thread.hook}\nChapter 1: {beat.title}. {beat.focus}\n"
                            f"About {minutes * WORDS_PER_MINUTE} words.", label="plain LLM baseline")
    judged = await judge(judge_ctx, draft.claims, cards, draft.narration)
    rows.append(score("baseline", draft.claims, {}, judged, e.ledger.total_usd, time.time() - t0, len(draft.narration.split())))
    print(f"  {tid} baseline: {rows[-1]['claims']} claims, misleading {rows[-1]['misleading_as_fact']}", flush=True)

    pasted = ROOT / "data" / "baseline_chatgpt" / f"{tid}.txt"
    if pasted.exists():
        text = pasted.read_text()
        sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 6][:16]
        claims = [Claim(id=f"c{i+1}", text=s, kind="history" if thread.mode == "history" else "lore", evidence_ids=[]) for i, s in enumerate(sents)]
        judged = await judge(judge_ctx, claims, cards, text)
        rows.append(score("chatgpt (pasted)", claims, {}, judged, 0.0, 0, len(text.split())))
    for r in rows:
        r["thread"] = tid
        r["evidence_cards"] = len(cards)
    rows.append({"thread": tid, "variant": "_judge_cost", "gen_cost_usd": round(judge_ctx.ledger.total_usd, 6)})
    return rows


def md(rows: list[dict]) -> str:
    data = [r for r in rows if not r["variant"].startswith("_")]
    variants = list(dict.fromkeys(r["variant"] for r in data))
    lines = ["# Claim accuracy: Loremaster vs a plain LLM, and what the Skeptic is worth", "",
             "Chapter 1 of each starter thread, generated from the **same evidence set**. An independent judge pass "
             "(fresh Skeptic call, citations ignored) grades every claim against that evidence. "
             "**Shown as fact but not backed** = the listener sees/hears it as fact, but the judge does not grade it Documented/Canon. "
             "Split into **overstated** (the evidence says it's debated, legend, conflicting or interpretation) and **unsourced** "
             "(nothing in the evidence set covers it; it may still be true, but the listener can't check it). "
             "Generated by `python scripts/accuracy_eval.py`. Real gpt-6-luna runs.", "",
             "| Variant | Claims | Judge-supported | Shown as fact, not backed | └ overstated | └ unsourced | Honestly flagged | Gen cost / chapter | Seconds |",
             "|---|---|---|---|---|---|---|---|---|"]
    for v in variants:
        r = [x for x in data if x["variant"] == v]
        n = sum(x["claims"] for x in r)
        sup = sum(x["claims"] * x["judge_supported_pct"] / 100 for x in r)
        mis = sum(x["misleading_as_fact"] for x in r)
        flg = sum(x["honestly_flagged"] for x in r)
        cost = sum(x["gen_cost_usd"] for x in r) / len(r)
        secs = sum(x["seconds"] for x in r) / len(r)
        ov = sum(x.get("overstated_as_fact", 0) for x in r)
        un = sum(x.get("unsourced_as_fact", 0) for x in r)
        lines.append(f"| **{v}** | {n} | {100*sup/max(n,1):.0f}% | **{mis} ({100*mis/max(n,1):.0f}%)** | {ov} | {un} | {flg} | ${cost:.5f} | {secs:.0f} |")
    lines += ["", "## By thread", "", "| Thread | Variant | Claims | Misleading | Cost | Examples of misleading claims |", "|---|---|---|---|---|---|"]
    for x in data:
        ex = "; ".join(e[:90] for e in (x.get("overstated_examples") or x["misleading_examples"])[:2])
        lines.append(f"| {x['thread']} | {x['variant']} | {x['claims']} | {x['misleading_as_fact']} | ${x['gen_cost_usd']:.5f} | {ex} |")
    jc = sum(r["gen_cost_usd"] for r in rows if r["variant"] == "_judge_cost")
    lines += ["", f"Judge cost for the whole eval: ${jc:.5f} (not part of the app's per-episode cost).",
              "", "Caveat: the judge is the same model family as the Skeptic, so it shares some blind spots. I spot-checked "
              "a sample of judge verdicts by hand against the linked sources (see the report)."]
    return "\n".join(lines) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", nargs="*", default=list(BY_ID))
    a = ap.parse_args()
    rows = []
    for t in a.threads:
        print(f"thread {t} …", flush=True)
        rows += await eval_thread(t)
    OUT.mkdir(exist_ok=True)
    (OUT / "accuracy_results.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    (OUT / "accuracy_results.md").write_text(md(rows))
    print("wrote output/accuracy_results.json and .md")


if __name__ == "__main__":
    asyncio.run(main())
