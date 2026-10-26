"""Re-capture every screenshot the report and slides use, from the current UI.

    python scripts/capture_report.py        # needs backend :8000 + frontend :5173 running (and an API key)

Runs with "Share anonymous usage stats" OFF, so these captures never touch the tester curiosity metrics.
Live calls it makes: one Ask, one interview answer, one concierge reply, one photo identification (~$0.003 total).
"""

from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "output" / "screenshots"
URL = "http://localhost:5173"
PHOTO = ROOT / "output" / "screenshots" / "snap_sample.jpg"   # any photo of a statue, coin or miniature
NO_STATS = "{onboarded:true, usage_stats:false, interests:['crossover','history'], worlds:['rome','star_wars']}"


def shot(page, name, selector=None, full=False):
    path = SHOTS / f"{name}.jpg"
    (page.locator(selector).first.screenshot if selector else lambda **k: page.screenshot(full_page=full, **k))(
        path=path, type="jpeg", quality=82)
    print("  saved", path.name, flush=True)


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])

        # 1) the 15-second quiz (fresh visitor; stats off from the start)
        q = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        q.add_init_script("localStorage.setItem('lm-prefs', JSON.stringify({usage_stats:false}))")
        q.goto(URL); q.wait_for_selector(".quiz"); time.sleep(0.5)
        for t in ("Real history", "Science"):
            q.locator(".quiz-opt", has_text=t).click(); time.sleep(0.2)
        shot(q, "60_quiz_1", ".quiz")
        q.locator(".quiz-next").click(); time.sleep(0.3)
        for w in ("Star Wars", "Rome & Byzantium"):
            q.locator(".quiz-opt", has_text=w).click()
        q.locator(".quiz-next").click(); time.sleep(0.3)
        q.locator(".quiz-opt", has_text="20 min").click(); time.sleep(0.5)
        q.locator(".quiz-next").click(); time.sleep(0.6)
        shot(q, "63_quiz_persona", ".quiz")
        q.context.close()

        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(f"if(!localStorage.getItem('lm-prefs'))localStorage.setItem('lm-prefs', JSON.stringify({NO_STATS}))")
        pg = ctx.new_page()

        # 2) home: hero, concierge + Snap, illustrated shelf
        pg.goto(URL); pg.wait_for_selector(".thread-cover"); time.sleep(1.2)
        shot(pg, "75_home")
        pg.fill(".concierge input", "20 minutes on the train, I love sieges and Byzantium")
        pg.click(".concierge button.primary"); pg.wait_for_selector(".concierge-reply", timeout=60000)
        if PHOTO.exists():
            pg.set_input_files(".snap input[type=file]", str(PHOTO)); pg.wait_for_selector(".snap-result", timeout=60000)
        time.sleep(0.6)
        shot(pg, "70_concierge", ".discover")
        pg.locator(".instant").scroll_into_view_if_needed(); time.sleep(0.8)
        shot(pg, "76_shelf")

        # 3) the demo story: Caesar's Rubicon -> Palpatine
        pg.locator(".instant .thread", has_text="Rubicon").first.click(); pg.wait_for_selector(".narration button.chip")
        pg.locator(".mini .play").click(); time.sleep(8)
        shot(pg, "90_caesar_player")
        shot(pg, "66_player_playing")
        pg.locator(".mini .play").click()
        chip = pg.locator(".narration .chip.g-debated").first
        chip = chip if chip.count() else pg.locator(".narration .chip").first
        chip.evaluate("e => e.scrollIntoView({block: 'center'})"); time.sleep(0.4)
        chip.click(); pg.wait_for_selector(".drawer"); time.sleep(0.6)
        shot(pg, "91_caesar_drawer"); shot(pg, "68_drawer"); pg.keyboard.press("Escape")

        # 4) Ask the narrator
        pg.click(".ask-btn"); pg.wait_for_selector(".ask-form input")
        pg.fill(".ask-form input", "Did George Lucas really base Palpatine on Julius Caesar?"); pg.press(".ask-form input", "Enter")
        pg.wait_for_selector(".answer", timeout=90000); time.sleep(1)
        shot(pg, "82_ask", ".ask-panel")
        pg.locator(".ask-panel .close").first.click(); time.sleep(0.3)

        # 5) Myth or Fact?
        pg.locator(".game.myth").scroll_into_view_if_needed(); time.sleep(0.4)
        pg.locator(".game.myth .game-buttons button").first.click(); time.sleep(0.8)
        shot(pg, "81_myth", ".game.myth")

        # 6) Interview the past
        pg.click("nav >> text=Interview"); pg.wait_for_selector(".char-cover"); time.sleep(1)
        shot(pg, "77_interview_guests")
        pg.locator(".char", has_text="Julius Caesar").click(); pg.wait_for_selector(".iv-form input")
        pg.fill(".iv-form input", "Did you really say 'the die is cast' at the Rubicon?"); pg.click(".iv-form button")
        pg.wait_for_selector(".bubble.them .in-char >> nth=1", timeout=120000); time.sleep(1)
        pg.locator(".bubble .ghost.preview").last.click(); time.sleep(0.2)   # stop auto-read audio
        shot(pg, "73_interview_chat")

        # 7) Library, Settings, Safety & transparency, light theme
        pg.click("nav >> text=Library"); pg.wait_for_selector(".lib-card"); time.sleep(1)
        shot(pg, "78_library")
        pg.click(".settings-btn"); pg.click(".settings-nav >> text=Appearance"); time.sleep(0.4)
        shot(pg, "79_settings")
        pg.click(".settings-nav >> text=Safety"); pg.wait_for_selector(".lab-card"); time.sleep(1.2)
        shot(pg, "80_settings_safety")
        pg.click(".settings-nav >> text=Appearance"); pg.click(".theme-opt.light"); time.sleep(0.6)
        pg.click("nav >> text=Listen"); pg.wait_for_selector(".thread-cover"); time.sleep(1)
        shot(pg, "83_home_light")
        pg.click(".settings-btn"); pg.click(".settings-nav >> text=Appearance"); pg.click(".theme-opt.dark"); time.sleep(0.6)
        b.close()


if __name__ == "__main__":
    main()
