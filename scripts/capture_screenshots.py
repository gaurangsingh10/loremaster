"""Capture report screenshots from the RUNNING app (backend :8000 + frontend :5173), including a live traced run.

    pip install -r requirements-dev.txt      # playwright; uses your installed Google Chrome
    python scripts/capture_screenshots.py

Writes JPEGs to output/screenshots/ and the traced episode id to output/screenshots/trace.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "output" / "screenshots"
URL = "http://localhost:5173"


def snap(page: Page, name: str, selector: str | None = None, full: bool = False) -> None:
    path = SHOTS / f"{name}.jpg"
    if selector:
        page.locator(selector).first.screenshot(path=path, type="jpeg", quality=82)
    else:
        page.screenshot(path=path, type="jpeg", quality=82, full_page=full)
    print("  saved", path.name, flush=True)


def wait_for(page: Page, js: str, timeout_s: float = 120) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if page.evaluate(js):
            return True
        time.sleep(0.4)
    return False


def nav(page: Page, label: str) -> None:
    page.locator("nav button", has_text=label).click()
    time.sleep(1.2)


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    trace: dict = {"steps": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(URL)
        page.wait_for_selector(".thread")
        time.sleep(1.5)
        snap(page, "01_home")

        # ---- live traced run: Rome -> Imperium of Man, 10 min
        page.locator(".thread", has_text="Imperium of Man").first.click()
        seen = set()
        t0 = time.time()
        while time.time() - t0 < 150 and not page.query_selector(".manuscript"):
            working = page.evaluate("[...document.querySelectorAll('.agent.working b')].map(b=>b.textContent)")
            for w in working:
                if w not in seen:
                    seen.add(w)
                    time.sleep(1.6 if w == "Researcher" else 0.6)  # let a tool call or two land in the log
                    snap(page, f"10_trace_{len(seen)}_{w.lower()}", ".player-grid")
                    trace["steps"].append({"agent": w, "t": round(time.time() - t0, 1)})
            time.sleep(0.3)
        page.wait_for_selector(".manuscript", timeout=60000)
        time.sleep(1.5)
        snap(page, "11_chapter_ready")
        page.evaluate("window.scrollTo(0, 0)")
        snap(page, "12_agents_and_meter", ".side")
        snap(page, "13_manuscript", ".manuscript")
        # tally + flagged claims
        page.locator(".tally").scroll_into_view_if_needed()
        snap(page, "14_tally", ".tally")
        # Is that true? drawer: prefer a flagged (non-documented) claim
        target = page.locator(".flag").first if page.locator(".flag").count() else page.locator(".chip").first
        target.click()
        time.sleep(0.8)
        snap(page, "15_drawer")
        page.locator(".drawer .close").click()
        # choice
        page.wait_for_selector(".choice-row button", timeout=60000)
        page.locator(".choice").scroll_into_view_if_needed()
        snap(page, "16_choice", ".choice")
        choice = page.locator(".choice-row button").first.inner_text()
        trace["choice"] = choice
        page.locator(".choice-row button").first.click()
        time.sleep(2)
        snap(page, "17_after_choice_working", ".player-grid")
        wait_for(page, "!!document.querySelector('.finale')", 200)
        time.sleep(1)
        page.locator(".finale").scroll_into_view_if_needed()
        snap(page, "18_finale", ".finale")
        ep = page.evaluate("fetch('http://localhost:8000/api/library').then(r=>r.json()).then(j=>j.episodes[0])")
        trace["episode"] = ep

        # ---- behind the curtain: costs, audit, safety lab
        nav(page, "Behind the curtain")
        snap(page, "20_curtain_costs", ".curtain section.card >> nth=0")
        snap(page, "21_audit", ".curtain section.card >> nth=2")
        cards = page.locator(".lab-card")
        plan = [(0, ["Run · defenses ON", "Run · defenses OFF"]), (1, ["Run · defenses ON", "Run · defenses OFF"]),
                (2, ["Run · defenses ON"]), (3, ["Run · defenses ON", "Run · defenses OFF"])]
        for idx, buttons in plan:
            card = cards.nth(idx)
            for label in buttons:
                card.locator("button", has_text=label).click()
                time.sleep(1)
                wait_for(page, "![...document.querySelectorAll('.lab-card button')].some(b=>b.textContent.includes('Running'))", 240)
            card.scroll_into_view_if_needed()
            time.sleep(0.5)
            name = ["30_safety_invented", "31_safety_poisoned", "32_safety_budget", "33_safety_harmful"][idx]
            card.screenshot(path=SHOTS / f"{name}.jpg", type="jpeg", quality=82)
            print("  saved", name, flush=True)

        nav(page, "Lore Library")
        snap(page, "40_library")
        nav(page, "Feedback")
        snap(page, "41_feedback", ".feedback")

        # mobile
        m = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        m.goto(URL)
        m.wait_for_selector(".thread")
        time.sleep(1)
        m.screenshot(path=SHOTS / "50_mobile_home.jpg", type="jpeg", quality=80)
        print("  saved 50_mobile_home", flush=True)
        browser.close()
    (SHOTS / "trace.json").write_text(json.dumps(trace, indent=1))
    print("trace:", json.dumps(trace)[:400])


if __name__ == "__main__":
    main()
