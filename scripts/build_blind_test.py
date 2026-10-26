"""Build the blind claim test for lore-expert testers (40K / Star Wars fans).

Takes 5 claims from finished Loremaster episodes on a thread and 5 claims from a plain-LLM baseline chapter on the
same topic, shuffles them, and writes a self-contained HTML sheet (no server needed: email it). Testers mark each claim
True / False / Not sure / Fan theory and click "Download my answers". Put returned JSON files in
output/user_tests/responses/ and run:  python scripts/build_blind_test.py --score

    python scripts/build_blind_test.py --thread republic-galactic-empire
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic_ai import Agent  # noqa: E402

from agents.common import EpisodeContext, run_agent  # noqa: E402
from catalog import BY_ID  # noqa: E402
from config import DB_PATH, build_model  # noqa: E402
from models import ChapterDraft, Episode  # noqa: E402
from tokenomics import Ledger  # noqa: E402

UT = ROOT / "output" / "user_tests"
BASELINE = ("You are the narrator of a popular history-and-fiction podcast. Write one engaging spoken chapter. After every "
            "sentence that states a checkable fact add a tag [c1], [c2]...; list each claim (id, text, kind, evidence_ids=[]).")


def instant_claims(instant_id: str, n: int) -> tuple[list[dict], dict]:
    """Claims from a pre-built Instant story (strict grading). Prefer a mix of grades, lore claims first."""
    b = json.loads((ROOT / "data" / "instant" / f"{instant_id}.json").read_text())
    chapters = [b["chapter1"], *b["branches"].values()]
    claims = [{"text": c["text"], "source": "loremaster", "grade": c["grade"], "episode": f"instant:{instant_id}"}
              for ch in chapters for c in ch["claims"] if c["grade"] != "Interpretation" and len(c["text"]) < 220]
    random.shuffle(claims)
    picked, seen = [], set()
    for c in claims:                                    # one of each grade first (variety)...
        if c["grade"] not in seen:
            picked.append(c); seen.add(c["grade"])
    for c in claims:                                    # ...then fill up to n
        if len(picked) >= n:
            break
        if c not in picked:
            picked.append(c)
    return picked[:n], b["thread"]


def loremaster_claims(thread_id: str, n: int) -> list[dict]:
    c = sqlite3.connect(DB_PATH)
    rows = c.execute("SELECT json FROM episodes WHERE json LIKE ? ORDER BY updated DESC", (f'%"id":"{thread_id}"%',)).fetchall()
    claims = []
    for (j,) in rows:
        ep = Episode.model_validate_json(j)
        for ch in ep.chapters:
            claims += [{"text": cl.text, "source": "loremaster", "grade": cl.grade, "episode": ep.id} for cl in ch.claims]
    random.shuffle(claims)
    lore = [x for x in claims if x["grade"] in ("Canon", "Legends", "Conflicting", "Fan theory")]
    rest = [x for x in claims if x not in lore]
    return (lore[: n // 2 + 1] + rest)[:n]


async def baseline_claims(thread_id: str, n: int, thread: dict | None = None) -> tuple[list[dict], float]:
    from models import Thread
    t = Thread(**thread) if thread else BY_ID[thread_id]
    e = EpisodeContext(episode_id=f"blind-{thread_id}", ledger=Ledger(budget_usd=0.02))
    agent = Agent(build_model(), output_type=ChapterDraft, instructions=BASELINE,
                  model_settings={"openai_reasoning_effort": "low", "max_tokens": 4000})
    d: ChapterDraft = await run_agent(e, "baseline", agent, f"Topic: {t.title}. {t.hook} About 700 words.", label="blind-test baseline")
    claims = [{"text": c.text, "source": "baseline", "grade": "ungraded"} for c in d.claims]
    random.shuffle(claims)
    return claims[:n], e.ledger.total_usd


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Loremaster · blind lore check</title>
<style>
body{{margin:0;background:#0b1020;color:#e9e4d8;font-family:-apple-system,Segoe UI,Inter,sans-serif}}
.wrap{{max-width:760px;margin:auto;padding:28px 18px 60px}}
.brand{{font-family:Georgia,serif;letter-spacing:.14em;color:#f0cf7e;text-transform:uppercase;font-size:14px}}
h1{{font-family:Georgia,serif;color:#f0cf7e;font-weight:600;margin:.2em 0 .3em;font-size:30px}}
p{{line-height:1.55}} .muted{{color:#9aa3b8;font-size:14px}}
.card{{background:linear-gradient(170deg,#efe3c8,#e4d4b0);color:#2b2218;border-radius:14px;padding:16px 18px;margin:14px 0;box-shadow:0 6px 20px rgba(0,0,0,.35)}}
.card p{{font-family:Georgia,serif;font-size:19px;margin:0 0 12px}} .num{{color:#8a5a10;font-weight:700;margin-right:6px}}
.opts{{display:flex;flex-wrap:wrap;gap:8px}} .opts label{{border:1.5px solid #a8916a;border-radius:999px;padding:7px 13px;cursor:pointer;font-size:14px;user-select:none}}
.opts input{{display:none}} .opts input:checked+span{{font-weight:700}} .opts label:has(input:checked){{background:#3a2a12;color:#f0cf7e;border-color:#3a2a12}}
input[type=text]{{background:#121a30;border:1px solid rgba(212,166,74,.4);color:#e9e4d8;border-radius:10px;padding:10px 12px;font-size:15px;width:100%;max-width:340px;box-sizing:border-box}}
button{{background:#d4a64a;color:#0b1020;border:0;border-radius:12px;padding:14px 20px;font-weight:700;font-size:16px;cursor:pointer}}
.progress{{position:sticky;top:0;background:#0b1020;padding:8px 0;color:#9aa3b8;font-size:13px;z-index:2}}
#ok{{color:#7fb77e;font-weight:600;margin-left:10px}}
</style></head><body><div class="wrap">
<div class="brand">✦ Loremaster</div>
<h1>Lore check: true or not?</h1>
<p>Thanks for helping! Below are <b>{n} claims</b> about <b>{topic}</b>. Some were written by one AI system and some by another. Judge each one from <i>your own knowledge</i>, with no Googling. It takes about 5 minutes.</p>
<p class="muted">Not sure? Pick “Not sure”, which is a useful answer too. “Fan theory / interpretation” means it's an opinion or a popular theory, not established lore.</p>
<p>Your name or alias<br><input type="text" id="tester" placeholder="e.g. Sam, 40K fan since 3rd ed."></p>
<p>Optional: how many minutes would it take you to <i>check</i> five of these online?<br><input type="text" id="google" placeholder="minutes"></p>
<div class="progress" id="prog">0 of {n} answered</div>
{items}
<p><b>Anything the AI got wrong, or a grade you'd argue with?</b><br><input type="text" id="notes" style="max-width:100%" placeholder="Optional comments"></p>
<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:8px">
<button onclick="wa()" style="background:#25D366;color:#06210f">Send my answers on WhatsApp</button>
<button onclick="cp()" style="background:transparent;color:#f0cf7e;border:1.5px solid #d4a64a">Copy answers</button>
<button onclick="dl()" style="background:transparent;color:#9aa3b8;border:1.5px solid #555">Download file</button>
</div><p id="ok"></p>
<p class="muted">“Send on WhatsApp” opens WhatsApp with your answers typed out: just pick Gaurang's chat and send. Nothing is uploaded anywhere else. Opened this inside WhatsApp and the buttons don't respond? Tap Share → Open in Safari/Chrome.</p>
<script>
const IDS={ids};
function upd(){{let k=IDS.filter(id=>document.querySelector('input[name='+id+']:checked')).length;document.getElementById('prog').textContent=k+' of '+IDS.length+' answered'}}
document.addEventListener('change',upd);
const CODE={{'True':'T','False':'F','Not sure':'N','Fan theory / interpretation':'I'}};
function code(){{const parts=IDS.map(id=>{{const r=document.querySelector('input[name='+id+']:checked');return id+'='+(r?CODE[r.value]:'-')}});
return 'LOREMASTER-BLIND v1 | sheet={sheet} | tester='+(document.getElementById('tester').value||'anon').replace(/[|\\n]/g,' ')+
' | mins='+(document.getElementById('google').value||'').replace(/[|\\n]/g,' ')+' | '+parts.join(' ')+' | notes='+(document.getElementById('notes').value||'').replace(/[|\\n]/g,' ')}}
function wa(){{const t=code();window.open('https://wa.me/?text='+encodeURIComponent(t),'_blank');document.getElementById('ok').textContent='Opening WhatsApp… choose Gaurang\\'s chat and press send.'}}
function cp(){{const t=code();(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>{{document.getElementById('ok').textContent='Copied! Paste it into a WhatsApp message to Gaurang.'}}).catch(()=>{{prompt('Copy this and send it to Gaurang:',t)}})}}
function dl(){{const a={{tester:document.getElementById('tester').value,google_minutes:document.getElementById('google').value,notes:document.getElementById('notes').value,answers:{{}}}};
for(const id of IDS){{const r=document.querySelector('input[name='+id+']:checked');a.answers[id]=r?r.value:null}}
const b=new Blob([JSON.stringify(a,null,1)],{{type:'application/json'}});const l=document.createElement('a');
l.href=URL.createObjectURL(b);l.download='loremaster_blind_'+(a.tester||'anon').replace(/\\W+/g,'_')+'.json';l.click();
document.getElementById('ok').textContent='Saved! Send that file back to Gaurang.'}}
</script></div></body></html>"""


def build(items: list[dict], topic: str, out: Path) -> None:
    rows = []
    for it in items:
        opts = "".join(f'<label><input type="radio" name="{it["id"]}" value="{v}"><span>{v}</span></label>'
                       for v in ("True", "False", "Not sure", "Fan theory / interpretation"))
        rows.append(f'<div class="card"><p><span class="num">{len(rows) + 1}.</span>{html.escape(it["text"])}</p><div class="opts">{opts}</div></div>')
    out.write_text(PAGE.format(n=len(items), topic=html.escape(topic), items="\n".join(rows),
                               ids=json.dumps([i["id"] for i in items]), sheet=out.stem.replace("blind_test_", "")))


def score() -> None:
    key = {k: v for f in UT.glob("blind_key_*.json") for k, v in json.loads(f.read_text()).items()}
    resp = [json.loads(p.read_text()) for p in (UT / "responses").glob("*.json")] if (UT / "responses").exists() else []
    # WhatsApp / copied answers: paste each message on its own line into output/user_tests/responses/*.txt
    letters = {"T": "True", "F": "False", "N": "Not sure", "I": "Fan theory / interpretation"}
    for p in (UT / "responses").glob("*.txt") if (UT / "responses").exists() else []:
        for line in p.read_text().splitlines():
            if "LOREMASTER-BLIND" not in line:
                continue
            fields = [f.strip() for f in line.split("|")]
            meta = {f.split("=", 1)[0]: f.split("=", 1)[1] for f in fields if "=" in f and " " not in f.split("=", 1)[0]}
            answers = {}
            for f in fields:
                for tok in f.split():
                    if "=" in tok and tok.split("=", 1)[0] in key:
                        k, v = tok.split("=", 1)
                        answers[k] = letters.get(v)
            resp.append({"tester": meta.get("tester", ""), "google_minutes": meta.get("mins", ""), "notes": meta.get("notes", ""), "answers": answers})
    if not resp:
        print("no responses yet in output/user_tests/responses/")
        return
    stats = {"loremaster": {"True": 0, "False": 0, "Not sure": 0, "Fan theory / interpretation": 0},
             "baseline": {"True": 0, "False": 0, "Not sure": 0, "Fan theory / interpretation": 0}}
    agree = total_graded = 0
    for r in resp:
        for cid, ans in r["answers"].items():
            k = key.get(cid)
            if not k or not ans:
                continue
            stats[k["source"]][ans] += 1
            if k["source"] == "loremaster":
                total_graded += 1
                fact = k["grade"] in ("Documented", "Canon")
                agree += (fact and ans == "True") or (not fact and ans != "True")
    lines = ["# Blind claim test results", "", f"{len(resp)} tester(s).", "", "| Source | True | False | Not sure | Fan theory |", "|---|---|---|---|---|"]
    for s, d in stats.items():
        lines.append(f"| {s} | {d['True']} | {d['False']} | {d['Not sure']} | {d['Fan theory / interpretation']} |")
    if total_graded:
        lines.append(f"\nTesters agreed with Loremaster's grade on {agree}/{total_graded} claims ({100*agree/total_graded:.0f}%).")
    g = [float(r["google_minutes"]) for r in resp if str(r.get("google_minutes", "")).replace(".", "", 1).isdigit()]
    if g:
        lines.append(f"Average time to verify 5 claims by Googling: {sum(g)/len(g):.1f} min (vs one tap per claim in the app).")
    (UT / "blind_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thread", default="republic-galactic-empire")
    ap.add_argument("--instant", help="draw Loremaster claims from a pre-built Instant story (e.g. rule-of-two)")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    UT.mkdir(parents=True, exist_ok=True)
    if a.score:
        score()
        return
    if a.instant:
        ours, thread = instant_claims(a.instant, 5)
        name, title = a.instant, thread["title"]
        base, cost = await baseline_claims(a.instant, 5, thread)
    else:
        ours = loremaster_claims(a.thread, 5)
        if len(ours) < 5:
            sys.exit("Play at least one episode of this thread first (need 5 Loremaster claims).")
        name, title = a.thread, BY_ID[a.thread].title
        base, cost = await baseline_claims(a.thread, 5)
    items = ours + base
    random.shuffle(items)
    prefix = name.split("-")[0][:3]
    for i, it in enumerate(items):
        it["id"] = f"{prefix}{i + 1}"
    build(items, title, UT / f"blind_test_{name}.html")
    (UT / f"blind_key_{name}.json").write_text(json.dumps({i["id"]: i for i in items}, indent=1))
    print(f"wrote output/user_tests/blind_test_{name}.html (+ answer key). baseline cost ${cost:.5f}")
    print("Loremaster grades in this sheet:", [i["grade"] for i in ours])


if __name__ == "__main__":
    asyncio.run(main())
