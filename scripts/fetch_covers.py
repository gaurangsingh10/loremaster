"""Download a picture for every instant-story card and interview guest (run once; results are committed).

Only freely licensed images: a Wikipedia article's free lead image, or a named Wikimedia Commons file (public-domain
paintings for the fictional stories and guests, so no Lucasfilm or Games Workshop artwork is used). Credits go to
frontend/public/covers/credits.json and show as each picture's tooltip.

    python scripts/fetch_covers.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from config import USER_AGENT  # noqa: E402

OUT = ROOT / "frontend" / "public" / "covers"
WP = "https://en.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"

# id -> "Wikipedia article" (its free lead image) or "File:..." (a specific Commons file)
COVERS = {
    # instant stories (crossovers use the real-history side)
    "rubicon-emergency-powers": "File:Domenico Ghirlandaio (1449-1494) (studio of) - Julius Caesar and the Crossing of the Rubicon (scene from the story of Alexander the Great) - E.372-2006 - Victoria and Albert Museum.jpg",
    "constantinople-siege-of-terra": "Fall of Constantinople",
    "templars-order-66": "File:Templars Burning.jpg",
    "inquisitions": "File:Pedro Berruguete Saint Dominic Presiding over an Auto-da-fe 1495.jpg",
    "varangian-custodes": "Varangian Guard",
    "sparta-space-marines": "Corinthian helmet",
    "vietnam-ewoks": "Vietnam War",
    "manhattan-death-star": "Trinity (nuclear test)",
    "mongols-white-scars": "Genghis Khan",
    "texas-law-medieval-spain": "Mosque–Cathedral of Córdoba",
    "nero-fiddle": "Great Fire of Rome",
    "library-of-alexandria": "Library of Alexandria",
    "bronze-age-collapse": "File:Medinet Habu Ramses III. Tempel Nordostwand Abzeichnung 01.jpg",
    "horus-heresy": "File:Pieter Bruegel the Elder - The Fall of the Rebel Angels - Google Art Project.jpg",
    "rule-of-two": "File:Paradise Lost 1.jpg",
    "placebo-effect": "Placebo",
    "discovery-myths": "File:Newtons apple tree at Woolsthorpe Manor.jpg",
    "telegraph-internet": "Transatlantic telegraph cable",
    "edison-tesla": "War of the currents",
    "filibuster-origins": "Filibuster in the United States Senate",
    "checks-and-balances": "The Federalist Papers",
    # interview guests
    "g-caesar": "Julius Caesar",
    "g-hypatia": "File:Hypatia portrait.png",
    "g-molay": "Jacques de Molay",
    "g-constantine": "Constantine XI Palaiologos",
    "g-elizabeth": "Elizabeth I",
    "g-madison": "James Madison",
    "g-newton": "Isaac Newton",
    "g-lovelace": "Ada Lovelace",
    "g-tesla": "Nikola Tesla",
    "g-bane": "File:GustaveDoreParadiseLostSatanProfile.jpg",
    "g-mothma": "File:Eugène Delacroix - La liberté guidant le peuple.jpg",
    "g-valdor": "Praetorian Guard",
}


def strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def commons_info(c: httpx.Client, file: str) -> dict | None:
    r = c.get(COMMONS, params={"action": "query", "titles": file, "prop": "imageinfo", "iiprop": "url|extmetadata",
                               "iiurlwidth": 720, "format": "json"}).json()
    page = next(iter(r["query"]["pages"].values()))
    if "imageinfo" not in page:
        return None
    ii = page["imageinfo"][0]; md = ii.get("extmetadata", {})
    return {"url": ii.get("thumburl") or ii["url"], "page": ii["descriptionurl"],
            "artist": strip(md.get("Artist", {}).get("value", ""))[:80],
            "license": strip(md.get("LicenseShortName", {}).get("value", ""))}


def article_image(c: httpx.Client, title: str) -> str | None:
    r = c.get(WP, params={"action": "query", "titles": title, "prop": "pageimages", "piprop": "name",
                          "pilicense": "free", "redirects": 1, "format": "json"}).json()
    page = next(iter(r["query"]["pages"].values()))
    return f"File:{page['pageimage']}" if page.get("pageimage") else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True) as c:
        for cid, src in COVERS.items():
            file = src if src.startswith("File:") else article_image(c, src)
            info = commons_info(c, file) if file else None
            if not info:
                print(f"  ✗ {cid}: no free image for {src}")
                continue
            img = c.get(info["url"])
            img.raise_for_status()
            dest = OUT / f"{cid}.jpg"
            dest.write_bytes(img.content)
            if shutil.which("sips"):  # macOS: 560 px JPEG, ~80 KB each
                subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "78", "-Z", "560", str(dest),
                                "--out", str(dest)], capture_output=True)
            credits[cid] = {"file": file, **info}
            print(f"  ✓ {cid}: {file} ({len(img.content)//1024} KB, {info['license']})")
    (OUT / "credits.json").write_text(json.dumps(credits, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
