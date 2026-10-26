# Design: why Loremaster looks and feels the way it does

**Concept: a dark illuminated manuscript.** History and 40K/Star Wars lore both live in old books, codices and holo-archives. So the app is a night-library: deep ink background, warm parchment pages, gold leaf accents.

- **Two layers of material.** The *app* (navigation, agents, cost meter) is dark ink. The *story* (thread cards, the chapter, the "Is that true?" drawer) is parchment. Your eye always knows what's content and what's machinery.
- **Type that sounds like the narrator.** Cinzel (Roman inscription capitals) for titles, Cormorant Garamond for narration (a bookish serif at 1.3rem, readable on a phone on a train), Inter for UI. Each chapter opens with an illuminated **drop cap**.
- **Thread cards as wax-seal emblems.** Each starter thread has a sigil (⚖ ☩ ✷ ✠) in a gold seal, tagged *Chronicle × Star Wars*, so the crossover is visible before you press play. Cards tilt and lift on hover, like picking a book off a shelf.
- **Honesty you can see but not trip over.** Every claim gets a small chip after its sentence: ✓ green for Documented/Canon, ◆ amber/purple/blue for Debated/Legend/Fan theory, ? red for Unsupported. Under each chapter, a tally ("14 claims checked: 11 Documented, 2 Debated, 1 Legend") and the flagged claims are listed so skimmers see the interesting ones. One tap opens a parchment **drawer** with the verdict, the Skeptic's note and the source snippet with a link.
- **Built for ears.** Big play button, ±15 s, speed 0.75–1.5×, and the sentence being read is highlighted in gold, so a glance at the phone finds your place. The browser voice reads sentence by sentence, which also avoids Chrome's long-speech cutoff.
- **The choice moment is the hook.** At the end of each chapter, three large branch buttons in the narrator's serif. While the next chapter is written, an animated quill shows what the agents are doing ("Showrunner is reshaping the arc around your choice…") so waiting feels like part of the show.
- **Agents you can watch.** The side panel lists the six agents with glyphs (⛨ ✦ ⌕ ❦ ⚖ ❧). The working agent pulses gold and shows its current tool call; finished agents turn green with their time. Below it, a **cost meter** fills against the $0.05 cap, with per-agent bars and live token counts. For graders it's the architecture diagram in motion; for listeners it's the "making-of."
- **Behind the curtain** is a deliberately plain, tabular page (runs, tokens, audit trail, Safety Lab with ON/OFF buttons), because evidence should look like evidence.
- **Lore Library** shelves every episode as a book spine you can reopen; paused threads say "paused at a choice" so tomorrow's commute picks up where today's ended.
- **Responsive.** Below 960 px the side panel drops under the story, for phone listening.

Why this should keep people listening: the commute use case needs zero-friction start (one tap on a card), something to glance at (highlighted sentence, chips), a reason to come back (the choice cliffhanger plus the Library), and trust (grades and sources one tap away).
