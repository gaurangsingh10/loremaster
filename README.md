# Loremaster: *Canon & Chronicle*

**An AI storyteller for long commutes that tells true stories from history, science, technology and politics, plus Star Wars and Warhammer 40K lore, and tells you how much of it is true.**

Pick a thread (e.g. *Roman Republic → Galactic Empire*) and a length (10 / 20 / 40 min). A passionate, lecture-style narrator tells the story out loud. At every chapter break you choose where it goes next. Tap any claim (**"Is that true?"**) to see its grade, Documented / Debated / Legend for history or Canon / Legends / Conflicting / Fan theory for Warhammer 40K and Star Wars, with the source snippet and link.

Six AI agents (gpt-6-luna) make each episode: **Guardian** (screens requests) → **Showrunner** (plans the arc) → **Researcher** (wiki evidence) → **Storyteller** (narration) → **Skeptic** (grades every claim, forces one rewrite if needed) → **Librarian** (further reading). Five more power the interactive features: **Answerer** (ask the narrator), **Quizmaster** (Myth or Fact? and Call it), **Identifier** (vision, for Snap & Story), **Interviewer** (in-character interviews with graded claims) and **Concierge** (recommends stories).

- MGT 409 *AI Foundations for Managers*, final project by Gaurang Singh
- Report: [`docs/report.html`](docs/report.html) · Slides: [`docs/slides.html`](docs/slides.html) · Agent harness: [`output/harness.md`](output/harness.md)

---

## Run it locally (about 5 minutes)

You need **Python 3.10+** and **Node.js 18+**.

> **Check first:** `python3 --version` must say 3.10 or newer. If it says 3.9 (common with Anaconda's base environment or the macOS system Python), the install fails with *"No matching distribution found for pydantic-ai-slim"*. Use a newer Python for the venv instead, e.g. `python3.12 -m venv .venv` (any of 3.10–3.13 works; get one from python.org). On Windows: `py -3.12 -m venv .venv`.

### 1. Put the key where the app can find it
The app reads `.env` from **this repo folder first, then the folder above it**. Graders: your `submissions/.env` with `PORTKEY_API_KEY` already works, so there's nothing to do.

Otherwise: `cp .env.example .env` and fill in `PORTKEY_API_KEY`. No key at all? The app still opens in **Demo mode** and plays a bundled sample episode.

### 2. Backend (terminal 1)

**Mac / Linux**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd backend
../.venv/bin/uvicorn main:app --port 8000
```

**Windows (PowerShell)**
```powershell
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd backend
..\.venv\Scripts\uvicorn main:app --port 8000
```
Check it: http://localhost:8000/api/health should say `"ok": true`.

### 3. Frontend (terminal 2)
```bash
cd frontend
npm install
npm run dev
```
Open **http://localhost:5173**.

**Try this first:** press any **⚡ Instant story** (e.g. *Friday the 13th → Order 66*). It starts in under a second, and every branch is pre-written. Press ▶ in the player at the bottom, tap a **D / ≈ / L / ?** mark after any sentence ("Is that true?"), then pick a branch. Next, type your own topic under **Make a new episode** to watch six agents write one live (~30 s; there's a **Stop writing** button). Then try **📸 Snap & Story** (upload a photo of a statue, coin or miniature), the **concierge** box on the home page, and the **Interview** tab (ask Julius Caesar about the Rubicon and watch his claims get graded). Finally, open **Settings → Safety & transparency** and use the **Safety Lab** and run *Poisoned wiki page*.

**Accounts (optional):** the first visit opens a 15-second quiz (skip any time). Create an account to save your narrator (man/woman · UK/US · deep/natural), story types (pick several), worlds and length. Accounts are stored locally in `data/loremaster.db`: passwords as salted scrypt hashes, with a bot check on sign-up and log-in.

**Interactive:** 💬 **Ask** pauses the story and answers your question (typed, or spoken in Chrome) with graded sources, read aloud. 🎯 **Call it** veils the reveal until you predict what happened. **Myth or Fact?** closes each chapter with three quick calls and a streak. Interactions are logged anonymously to `output/interaction_log.json`, and **Settings → Safety & transparency** shows the curiosity metrics. Settings also has a light or dark theme, text size, reduced motion, playback options, password change, sign out of other devices, account deletion and a usage-stats opt-out.

**Settings** (top right): narrator · story types · **night or day theme**, text size, reduced motion · playback (read answers aloud, keep playing after a choice) · account (display name, change password, sign out of other devices, delete account) · privacy (turn off the anonymous usage log, clear device data) · **Safety & transparency** (Safety Lab, costs, curiosity metrics). The **Library** shows one card per story with Continue listening, search and filters.

**Player:** Space = play/pause · ←/→ = 15 s · Shift+←/→ = previous/next section. Drag the scrubber or click a section marker. Your position in each chapter is remembered.

### Optional: the natural neural narrator (deep British baritone)
```bash
.venv/bin/pip install -r requirements-voice.txt
.venv/bin/python scripts/get_voice.py      # downloads the Kokoro voice model (~340 MB) into models/
```
Restart the backend. Without this step the narrator uses your computer's built-in voice (macOS `say` / Windows SAPI), or the browser's voice as a last resort. Audio is rendered per paragraph (first paragraph in ~3–4 s) and cached in `data/audio/`.

*(Optional single-server mode: `cd frontend && npm run build`, then the backend serves the UI at http://localhost:8000.)*

---

## Data modes (big-data rule)

| Mode | What it does | How |
|---|---|---|
| **live** (default) | Searches Wikipedia, Wookieepedia and the Warhammer 40k Wiki through their free, keyless APIs, and caches every page it reads into `data/cache/pages/` | nothing to set |
| **cached** | Uses only the bundled pages in `data/cache/pages/` (about 90 files covering the 4 starter threads). No internet needed except for the model | `LOREMASTER_DATA_MODE=cached` in `.env` |
| **demo** | No API key needed and no model calls. Plays the bundled sample episode (`data/cache/episodes/sample_episode.json`) | `LOREMASTER_DATA_MODE=demo`, or just run with no key |

If a wiki is slow or down in live mode, the app automatically falls back to the cache.

## Keys

| Key | Needed? | Used for |
|---|---|---|
| `PORTKEY_API_KEY` | one of these two, for live episodes | every agent via the course Portkey gateway, **gpt-6-luna only** (hard-coded) |
| `OPENAI_API_KEY` (as your own key) | one of these two | if no Portkey key is in `.env`, the same agents call OpenAI directly with gpt-6-luna. If both are present, Portkey is used. Keys in `.env` files take priority over keys exported in your shell. |
| (`OPENAI_API_KEY`, voice) | optional | also used for narration only if the free Kokoro voice isn't installed (OpenAI TTS, paid). |

No other keys. The wiki and Open Library APIs are keyless.

## Scripts (evidence for the report)

All scripts run from the repo root with the venv's Python (`.venv/bin/python` on Mac, `.venv\Scripts\python` on Windows):

| Command | What it produces |
|---|---|
| `python scripts/cli.py --thread republic-galactic-empire --minutes 10` | One episode headless: narration, every grade, per-agent tokens and $ |
| `python scripts/safety_test.py` | The 4 Safety Lab attacks, defenses ON vs OFF → `output/safety_results.md` |
| `python scripts/cache_test.py` | The same 3 episodes with vs without prompt caching → `output/cache_test.md` |
| `python scripts/accuracy_eval.py` | Claim accuracy: full / Skeptic-lite / no Skeptic / plain LLM → `output/accuracy_results.md` |
| `python scripts/build_blind_test.py --instant rule-of-two` | Blind true/false sheet for fan testers, shareable over WhatsApp → `output/user_tests/` (`--score` tallies JSON files and pasted WhatsApp replies in `responses/*.txt`) |
| `python scripts/build_instant.py` | (Re)builds the 21 ⚡ Instant stories in `data/instant/` (chapter 1 + all 3 branches each; ~$0.27 total) |
| `python scripts/build_games.py` | (Re)builds Myth or Fact? + Call it games for every instant-story chapter (~$0.03 total) |
| `python scripts/capture_report.py` | Re-captures every screenshot the report and slides use (usage stats off, so tester metrics stay clean; ~$0.003) |
| `python scripts/fetch_covers.py` | Downloads the public-domain / CC card pictures from Wikimedia Commons into `frontend/public/covers/` (credits in `credits.json`) |
| `python scripts/costs.py` | Cost per episode / user / month and at 100 and 10,000 users, from `output/usage_log.json` |

## Where things are

```
backend/   FastAPI app (main.py), pipeline.py (orchestration), agents/ (one file per agent),
           prompts/ (one prompt per agent + shared house rules + narrator style guide), tools.py (wiki tools + sanitizer),
           tokenomics.py (per-agent ledger + budget cap), safety.py (Safety Lab), models.py (all typed contracts)
frontend/  React + Vite + TypeScript UI
data/      cache/ (bundled wiki pages + sample episode), fixtures/ (poisoned page for the safety demo)
output/    harness.md, design.md, audit_trail.json (append-only), usage_log.json, test results, user tests
docs/      report.html, slides.html
```

## Limits

- Narration is AI-written. The grades are AI-checked against wiki snippets, not against primary sources.
- Fan wikis are the canon authority here. Lexicanum (40K) blocks bots, so the Warhammer 40k Fandom wiki is used instead.
- The browser voice depends on your OS's installed voices. Chrome and Safari on Mac sound best.
- Accounts have no email verification or forgotten-password reset (you can change a password while signed in).
- Card pictures are public-domain or CC images from Wikimedia Commons; the Star Wars and 40K stories use classic art, not franchise artwork.

Unofficial fan and educational project. Not affiliated with Lucasfilm, Disney or Games Workshop. Wiki text is used under CC BY-SA with links on every claim.
