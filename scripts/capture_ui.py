"""Capture screenshots of the current UI (no paid live trace): onboarding quiz, personalized home, player with the
scrubber, the "Is that true?" drawer, the choice dock, the Stop button, the profile page and mobile views.

    python scripts/capture_ui.py        # needs backend :8000 + frontend :5173 running

Creates a throwaway test account (*@loremaster.test) and deletes it at the end.
"""

from __future__ import annotations

import secrets
import sqlite3
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "output" / "screenshots"
URL = "http://localhost:5173"


def shot(page, name, selector=None, full=False):
    path = SHOTS / f"{name}.jpg"
    (page.locator(selector).first.screenshot if selector else lambda **k: page.screenshot(full_page=full, **k))(path=path, type="jpeg", quality=82)
    print("  saved", path.name, flush=True)


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    pw = "t-" + secrets.token_urlsafe(10)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.goto(URL); pg.wait_for_selector(".quiz"); time.sleep(0.6)
        shot(pg, "60_quiz_1")
        pg.locator(".quiz-opt", has_text="history behind the lore").click(); time.sleep(0.4)
        for w in ("Warhammer 40K", "Rome & Byzantium", "Myths & mysteries"):
            pg.locator(".quiz-opt", has_text=w).click()
        shot(pg, "61_quiz_worlds", ".quiz"); pg.locator(".quiz-next").click(); time.sleep(0.3)
        pg.locator(".quiz-opt", has_text="20 min").click(); time.sleep(0.5)
        shot(pg, "62_quiz_narrator", ".quiz"); pg.locator(".quiz-next").click(); time.sleep(0.5)
        shot(pg, "63_quiz_persona", ".quiz")
        pg.locator(".quiz button", has_text="Save to an account").click(); time.sleep(0.4)
        pg.fill(".account input[autocomplete=name]", "Gaurang"); pg.fill(".account input[type=email]", "screens@loremaster.test")
        pg.locator(".account .pw-wrap input").nth(0).fill(pw)
        pg.locator(".account .eye").first.click()                      # reveal (own screen only)
        pg.locator(".account .pw-wrap input").nth(1).fill(pw)
        pg.locator(".account .robot").click(); time.sleep(2.2)          # bot check: tick + human-speed delay
        pg.locator(".account .eye").first.click()                      # hide again: never screenshot a password
        shot(pg, "64_signup", ".account")
        pg.locator(".account .primary").click(); time.sleep(1.2)
        pg.evaluate("window.getSelection().removeAllRanges()")
        shot(pg, "65_home_personal")
        # player
        pg.locator(".thread.picked").first.click(); pg.wait_for_selector(".mini"); time.sleep(0.8)
        pg.locator(".mini .play").click(); time.sleep(9)
        box = pg.locator(".track-wrap input").bounding_box()
        pg.mouse.click(box["x"] + box["width"] * 0.33, box["y"] + box["height"] / 2); time.sleep(6)
        shot(pg, "66_player_playing")
        shot(pg, "67_mini_player", ".mini")
        pg.locator(".mini .play").click()
        chip = pg.locator(".narration .chip.g-interp, .narration .chip.g-debated, .narration .chip.g-legend, .narration .chip.g-bad").first
        chip = chip if chip.count() else pg.locator(".narration .chip").first
        chip.evaluate("e => e.scrollIntoView({block: 'center'})"); time.sleep(0.4)
        chip.click(); pg.wait_for_selector(".drawer"); time.sleep(0.6)
        shot(pg, "68_drawer"); pg.keyboard.press("Escape")
        pg.locator(".tally").scroll_into_view_if_needed(); time.sleep(0.8)
        shot(pg, "69_tally_choice")
        pg.locator(".account-btn").click(); time.sleep(0.8)
        shot(pg, "70_profile", full=True)
        # live episode -> waiting screen -> Stop
        pg.locator("nav button", has_text="Listen").click(); time.sleep(0.8)
        pg.fill(".create .ask input", "Why did the Byzantine Empire last a thousand years?")
        pg.locator(".create .ask button").click(); pg.wait_for_selector(".waiting"); time.sleep(6)
        shot(pg, "71_waiting_stop", ".stage")
        pg.locator(".stop").first.click(); time.sleep(3)
        shot(pg, "72_stopped", ".stage")
        # mobile
        m = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=2).new_page()
        m.goto(URL); m.wait_for_selector(".quiz"); time.sleep(0.4)
        shot(m, "73_mobile_quiz")
        m.locator(".quiz-skip").click(); time.sleep(0.5)
        m.locator(".instant .thread").first.click(); m.wait_for_selector(".mini"); time.sleep(1.2)
        shot(m, "74_mobile_player")
        b.close()
    c = sqlite3.connect(ROOT / "data" / "loremaster.db")
    c.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@loremaster.test')")
    c.execute("DELETE FROM users WHERE email LIKE '%@loremaster.test'"); c.commit()
    print("test account removed")


if __name__ == "__main__":
    main()
