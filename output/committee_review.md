# Expert committee review (2026-10-23)

Five AI reviewer agents, each with a persona, used the **running** app in real Chrome (Playwright, desktop and phone viewports), read finished episodes through the API, and returned ranked recommendations. Their screenshots are in the session scratchpad. This file records what they found and what changed.

| Reviewer | Headline finding |
|---|---|
| **UX designer** | Strong visual identity, but the two signature features (choosing a branch, "Is that true?") were buried under ~2,000px of text and never explained. Listener and developer tabs were mixed in the nav. The mode toggle silently did nothing on curated cards. |
| **Commuter (phone, Metro-North)** | Wouldn't use it on the train yet: play controls scrolled away, narration "sounds like a careful Wikipedia summary", and the same hedges repeated ("a lens, not a family tree"). Branch labels too dry to tempt. Measured live waits: 34 s to chapter 1, 52 s after a choice. |
| **Lore expert (40K / Star Wars)** | No false lore found in 47 claims, but **46/47 lore claims were graded Canon**: the Skeptic checked paraphrase, not canon status. Disputed a Legends grade and a Sifo-Dyas claim. Crossovers sometimes contained no lore at all, and ignored documented creator intent (Lucas on Caesar). |
| **Historian** | ~95% of history claims Documented. "Documented" meant "a snippet says it". **The Texas 'Muslim Spain' myth itself was never graded.** Narrator framing was graded as fact. Flagged an obscure "Villiyet" treatise line and an overstated Catiline claim. |
| **Accessibility / audio engineer** | **Root cause of silent audio:** every live update rebuilt the chapter object, which re-ran the narrator's `load()` → `speechSynthesis.cancel()` five times in ~30 ms; utterances were also garbage-collected. Chips relied on `color-mix()` (unformatted on older browsers). Drawer had no Escape or focus handling; contrast was below 4.5:1 on some parchment labels; no reduced-motion support. |

## What I changed in response

**Audio (owner: "I can't hear anything"; "sound is very artificial")**
- Narration is now real audio files rendered by the backend and played as a per-paragraph playlist with prefetch (`backend/audio.py`, `frontend/src/audioPlayer.ts`). The browser voice is only a hardened fallback (kept references, generation token, `resume()`, `voiceschanged`).
- **Kokoro** neural voice (offline, free, Apache-2.0): deep British male "George" by default, with Lewis, Fable, Onyx and a George×Lewis blend selectable. The first paragraph is ready in ~4 s, and the rest renders while you listen. Fallbacks: macOS `say` → Windows SAPI → browser.
- Media Session API, so lock-screen and headphone controls work.

**Speed (owner: "make content generation fast")**
- **15 ⚡ Instant stories**, chosen from the committee's topic suggestions, each with chapter 1 **and all three branches** pre-written by the same agents. Measured: chapter visible **0.36 s** after tapping; branch chapter **0.08 s** after choosing. Build cost $0.20 for all 15.

**UX**
- A sticky bottom mini-player (play, paragraph skip, speed, voice), and the paragraph being read is highlighted.
- The choice bar docks at the bottom when you reach the end of the chapter or the audio ends. Branches are written as teasers. A 15 s auto-continue lets commuters keep their phone in their pocket.
- **Stop writing** button on every wait screen ("Stopped. Nothing more will be spent."); the backend cancels the task, and stopped episodes can be resumed by choosing a branch.
- Wait screen: a skeleton with the planned chapter titles, a live step ("Researcher is reading: …") and an elapsed timer, plus "or play an instant story with no wait".
- Nav is now Listen / Now playing (live dot) / Library / How it works, with Feedback in the footer. "Continue where you left off" sits at the top of the home page. The Library is grouped by thread, failed runs are hidden, and costs are removed from the listener's view.
- Chips are solid colored marks with letters (D/C ≈ ≠ L F i ?), and the tally pills filter the claim list. A one-time tip explains them. The agents and cost meter fold into "Behind the scenes".
- a11y: drawer has `aria-modal`, focus on open, Escape to close, focus returns to the chip; chip `aria-label`s; `:focus-visible`; skip link; darker parchment labels (#6b450c); `prefers-reduced-motion`.

**Grading and narration**
- New **Interpretation** grade for narrator framing and history↔fiction parallels (never Documented/Canon).
- Skeptic grades the claim **as stated**, with worked examples ("X argued Y" vs "Y"), a **thin-sourcing** cap at Debated, canon **status** for lore (hedged or multiply-told → Conflicting), the /Legends ceiling only when no canon card supports the claim, and creator-intent claims graded from Wikipedia.
- Storyteller must state a popular myth as its own claim so it gets graded; crossover chapters need ≥⅓ lore claims and a specific named parallel; tics ("Here's my take") at most once per chapter; no repeated "not a chain of influence" disclaimers; cold-open scenes, quotes from cards, a two-sentence recap, cause vs. sequence.
- Result on the 15 instant stories: 399 Documented, 222 Canon, **146 Interpretation, 44 Legends, 20 Debated, 8 Conflicting, 14 Unsupported, 1 Legend, 1 Fan theory**, versus nearly all Documented/Canon before.

**Not done yet (honest)**
- Myths are sometimes phrased as "a popular image portrays…, but the evidence doesn't establish it" (graded Unsupported) instead of stated plainly (graded Legend).
- No streaming of narration text while it's written; no speculative pre-generation for live episodes.
- Fan-wiki provenance (Codex vs. Black Library) is not shown; there's no curated non-Wikipedia secondary-source tier.
