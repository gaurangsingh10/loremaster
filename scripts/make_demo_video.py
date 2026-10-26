"""Record the ~3-minute demo video: Chrome is driven through the shot list while Playwright records the screen;
a voiceover in the app's own neural voice (Kokoro) is laid over each shot, with short clips of the real narrator
and of Caesar's interview answer spliced in. Waits for live AI calls are cut out.

    python scripts/make_demo_video.py      # needs backend :8000 + frontend :5173, an API key, Kokoro and ffmpeg

Output: output/demo/loremaster_demo.mp4 (git-ignored; upload it to Canvas). Runs with usage stats off.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import audio  # noqa: E402

URL, API = "http://localhost:5173", "http://localhost:8000"
OUT = ROOT / "output" / "demo"
WORK = OUT / "work"
PHOTO = ROOT / "output" / "screenshots" / "snap_sample.jpg"
VO_VOICE = "female-us-natural"      # presenter; the in-app narrator is the deep UK man
W, H = 1440, 900

VO = {
    "home": "This is Loremaster, an AI storyteller for your commute. It tells long, gripping stories about history, science, "
            "politics, and the lore of Star Wars and Warhammer 40K. And it tells you how much of each story is true.",
    "quiz": "A fifteen-second quiz picks the narrator and the kinds of stories you like. You can pick several at once.",
    "story": "Twenty-one stories start instantly. This one braids Caesar crossing the Rubicon with Palpatine's emergency powers. "
             "The narrator is a neural voice running right on the laptop, for free. Here it is.",
    "drawer": "Every sentence carries a grade. Caesar's famous line, let the die be cast? Debated. "
              "Ancient writers report it differently, and here is the source.",
    "ask": "You can pause and ask the narrator anything. The answer is researched, graded, and read aloud, "
           "and it refuses to overclaim.",
    "myth": "Each chapter ends with a quick game of Myth or Fact. Then you choose where the story goes next, "
            "and the next chapter is already waiting.",
    "interview": "You can also interview the past. Caesar answers in character, but every claim he makes is graded, "
                 "because Caesar always flattered Caesar. Listen.",
    "snap": "Or photograph something in a museum. A vision agent says what it probably is, how sure it is, and which clues it used, "
            "then turns it into a story.",
    "safety": "Behind the scenes, eleven AI agents write and fact-check every story, for about a cent an episode. "
              "Here, a poisoned wiki page hides instructions for the AI. The defenses strip them out before any agent ever reads them.",
    "outro": "Your library picks up where you left off, in a night or day theme. Loremaster: curiosity you can trust.",
}


def vo_wav(key: str) -> Path:
    path = WORK / f"vo_{key}.wav"
    if not path.exists():
        audio._render_kokoro(VO[key], path, VO_VOICE)
    return path


def dur(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def record() -> tuple[Path, list, dict]:
    marks: list[tuple[str, float]] = []          # (label, seconds since recording start)
    clips: dict[str, str] = {}                   # name -> audio URL to splice in
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": W, "height": H})
        ctx.add_init_script("localStorage.setItem('lm-prefs', JSON.stringify({onboarded:true, usage_stats:false, interests:[], worlds:[]}));"
                            "")
        pg = ctx.new_page()
        # Chrome's own screencast (no extra download): every changed frame arrives with a wall-clock timestamp
        frames: list[tuple[float, Path]] = []
        cdp = ctx.new_cdp_session(pg)
        def on_frame(ev):
            path = WORK / f"f{len(frames):05d}.jpg"
            import base64
            path.write_bytes(base64.b64decode(ev["data"]))
            frames.append((ev["metadata"]["timestamp"], path))
            cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 88, "maxWidth": W, "maxHeight": H, "everyNthFrame": 1})
        t0 = time.time()
        mark = lambda label: marks.append((label, time.time() - t0))   # noqa: E731

        def on_response(r):
            u = r.url
            if "/api/audio/" in u and "/manifest" not in u and "story" not in clips:
                clips["story"] = u
            if "/api/answer/" in u and "/audio" in u and clips.get("_want") == "interview":
                clips["interview"] = u; clips["_want"] = ""
        pg.on("response", on_response)
        slow = lambda sel, text: pg.locator(sel).first.type(text, delay=45)   # noqa: E731

        pg.goto(URL); pg.wait_for_selector(".thread-cover"); time.sleep(0.8)
        mark("home"); time.sleep(2.5)
        pg.mouse.wheel(0, 650); time.sleep(2.5); pg.mouse.wheel(0, 500); time.sleep(2.0)

        mark("quiz"); pg.locator("button", has_text="personalize (15 s)").first.click(); pg.wait_for_selector(".quiz"); time.sleep(0.8)
        for t in ("history behind the lore", "Real history", "Science"):
            pg.locator(".quiz-opt", has_text=t).first.click(); time.sleep(0.5)
        pg.locator(".quiz-next").click(); time.sleep(0.6)
        for w in ("Star Wars", "Rome & Byzantium"):
            pg.locator(".quiz-opt", has_text=w).click(); time.sleep(0.4)
        pg.locator(".quiz-next").click(); time.sleep(0.6)
        pg.locator(".quiz-opt", has_text="20 min").click(); time.sleep(0.9)
        pg.locator(".quiz-next").click(); time.sleep(1.8)
        pg.locator(".quiz button.primary").last.click(); pg.wait_for_selector(".instant .thread"); time.sleep(1.2)

        mark("story"); pg.locator(".instant .thread", has_text="Rubicon").first.scroll_into_view_if_needed(); time.sleep(1.0)
        pg.locator(".instant .thread", has_text="Rubicon").first.click(); pg.wait_for_selector(".narration button.chip"); time.sleep(1.2)
        pg.locator(".mini .play").click(); time.sleep(9)
        box = pg.locator(".track-wrap input").bounding_box()
        pg.mouse.click(box["x"] + box["width"] * 0.12, box["y"] + box["height"] / 2); time.sleep(4)
        pg.locator(".mini .play").click(); time.sleep(0.5)

        mark("drawer"); chip = pg.locator(".narration .chip.g-debated").first
        chip.evaluate("e => e.scrollIntoView({block: 'center'})"); time.sleep(0.8); chip.click(); pg.wait_for_selector(".drawer"); time.sleep(6.5)
        pg.keyboard.press("Escape"); time.sleep(0.5)

        mark("ask"); pg.click(".ask-btn"); pg.wait_for_selector(".ask-form input"); time.sleep(0.6)
        slow(".ask-form input", "Did George Lucas really base Palpatine on Julius Caesar?"); pg.press(".ask-form input", "Enter")
        mark("cut_start"); pg.wait_for_selector(".answer", timeout=120000); mark("cut_end"); time.sleep(7)
        pg.locator(".ask-panel .close").first.click(); time.sleep(0.6)

        mark("myth"); pg.locator(".game.myth").scroll_into_view_if_needed(); time.sleep(1.2)
        pg.locator(".game.myth .game-buttons button").first.click(); time.sleep(3)
        if pg.locator(".choice-pill").count():
            pg.click(".choice-pill")
        pg.wait_for_selector(".choice-row button", timeout=30000); time.sleep(1.5)
        pg.locator(".choice-row button").first.click(); time.sleep(3.5)

        mark("interview"); pg.click("nav >> text=Interview"); pg.wait_for_selector(".char-cover"); time.sleep(2.2)
        pg.locator(".char", has_text="Julius Caesar").click(); pg.wait_for_selector(".iv-form input"); time.sleep(1)
        clips["_want"] = "interview"
        slow(".iv-form input", "What happened on the Ides of March? Did you see it coming?"); pg.click(".iv-form button")
        mark("cut_start"); pg.wait_for_selector(".bubble.them .in-char >> nth=1", timeout=120000); mark("cut_end"); time.sleep(9)

        mark("snap"); pg.click("nav >> text=Listen"); pg.wait_for_selector(".snap"); pg.locator(".discover").scroll_into_view_if_needed(); time.sleep(1.2)
        pg.set_input_files(".snap input[type=file]", str(PHOTO))
        mark("cut_start"); pg.wait_for_selector(".snap-result", timeout=60000); mark("cut_end"); time.sleep(6)

        mark("safety"); pg.click(".settings-btn"); pg.click(".settings-nav >> text=Safety"); pg.wait_for_selector(".lab-card"); time.sleep(1.5)
        card = pg.locator(".lab-card", has_text="Poisoned wiki page"); card.scroll_into_view_if_needed(); time.sleep(1)
        card.locator("button").first.click()
        mark("cut_start")
        pg.wait_for_function("[...document.querySelectorAll('.lab-card')].some(c => c.innerText.includes('Poisoned wiki page') && /quarantin|blocked|✅/i.test(c.innerText))", timeout=180000)
        mark("cut_end"); time.sleep(7)

        mark("outro"); pg.click("nav >> text=Library"); pg.wait_for_selector(".lib-card"); time.sleep(3)
        pg.click(".settings-btn"); pg.click(".settings-nav >> text=Appearance"); time.sleep(0.8); pg.click(".theme-opt.light"); time.sleep(1.2)
        pg.click("nav >> text=About"); pg.wait_for_selector(".about"); time.sleep(3.5)
        pg.click(".settings-btn"); pg.click(".settings-nav >> text=Appearance"); pg.click(".theme-opt.dark"); time.sleep(0.3)
        pg.click("nav >> text=About"); time.sleep(2.5)
        mark("end")
        cdp.send("Page.stopScreencast"); time.sleep(0.3); ctx.close(); b.close()
    video = frames_to_video(frames, t0, time.time() - t0 if not marks else marks[-1][1] + 0.5)
    clips.pop("_want", None)
    return video, marks, clips


def frames_to_video(frames, t0, total) -> Path:
    """Variable-rate screencast frames -> constant 30 fps video whose time zero is t0."""
    lines = []
    pts = [(max(0.0, ts - t0), path) for ts, path in frames]
    if pts and pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    for (t, path), nxt in zip(pts, pts[1:] + [(total, None)]):
        lines.append(f"file '{path.name}'\nduration {max(0.001, nxt[0] - t):.3f}\n")
    lines.append(f"file '{pts[-1][1].name}'\n")
    lst = WORK / "frames.txt"; lst.write_text("".join(lines))
    raw = WORK / "raw.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst.name,
                    "-vf", f"fps=30,scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", raw.name], check=True, cwd=WORK)
    print(f"  {len(frames)} frames -> {raw.name} ({dur(raw):.0f} s)", flush=True)
    return raw


def shots_from(marks):
    """Turn marks into shots: (key, [(start, end), ...]) with the cut intervals removed."""
    names = [m for m in marks if m[0] not in ("cut_start", "cut_end")]
    shots = []
    for (key, a), (_, b) in zip(names, names[1:]):
        cuts = [(s, e) for (k1, s), (k2, e) in zip(marks, marks[1:]) if k1 == "cut_start" and k2 == "cut_end" and a <= s < b]
        parts, cur = [], a
        for s, e in cuts:
            parts.append((cur, s + 0.6)); cur = e - 0.4      # keep a beat of the click and of the result appearing
        parts.append((cur, b))
        shots.append((key, parts))
    return shots


def build(video: Path, marks, clips) -> Path:
    fetched = {}
    for name, url in clips.items():
        dest = WORK / f"clip_{name}.audio"
        dest.write_bytes(httpx.get(url, timeout=120).content); fetched[name] = dest
    pieces = []
    for i, (key, parts) in enumerate(shots_from(marks)):
        vo = vo_wav(key)
        audio_inputs = [vo] + ([fetched[key]] if key in fetched else [])
        aud_len = dur(vo) + (min(dur(fetched[key]), 9.0) + 0.3 if key in fetched else 0) + 0.5
        vis_len = sum(e - s for s, e in parts)
        target = max(vis_len, aud_len)
        vf = "".join(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{j}];" for j, (s, e) in enumerate(parts))
        vf += "".join(f"[v{j}]" for j in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0,fps=30,"
        vf += f"tpad=stop_mode=clone:stop_duration={max(0, target - vis_len):.3f},scale={W}:{H}[vout];"
        if len(audio_inputs) == 2:
            af = "[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];[2:a]atrim=0:9,aresample=48000,aformat=channel_layouts=stereo,afade=t=out:st=8.2:d=0.8[a2];" \
                 "[a1]apad=pad_dur=0.3[a1p];[a1p][a2]concat=n=2:v=0:a=1,apad[aout]"
        else:
            af = "[1:a]aresample=48000,aformat=channel_layouts=stereo,apad[aout]"
        out = WORK / f"shot_{i:02d}_{key}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video)] + sum((["-i", str(a)] for a in audio_inputs), []) + [
            "-filter_complex", vf + af, "-map", "[vout]", "-map", "[aout]", "-t", f"{target:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "22", "-c:a", "aac", "-b:a", "160k", str(out)]
        subprocess.run(cmd, check=True)
        pieces.append(out)
        print(f"  shot {i + 1:2d} {key:10s} video {vis_len:5.1f}s audio {aud_len:5.1f}s -> {target:5.1f}s", flush=True)
    lst = WORK / "list.txt"; lst.write_text("".join(f"file '{p.name}'\n" for p in pieces))
    final = OUT / "loremaster_demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    "-movflags", "+faststart", str(final)], check=True, cwd=WORK)
    return final


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required (brew install ffmpeg)")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    for k in VO:
        vo_wav(k)
    print("voiceover rendered; recording…", flush=True)
    video, marks, clips = record()
    (WORK / "marks.json").write_text(json.dumps({"marks": marks, "clips": clips}, indent=1))
    final = build(video, marks, clips)
    print(f"done: {final} ({dur(final):.0f} s, {final.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
