"""Build the self-contained deliverables: replace {{img:name}} in docs/src/*.src.html with base64 screenshots.

    python scripts/embed_images.py      # -> docs/report.html, docs/slides.html
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "output" / "screenshots"


def embed(src: Path, out: Path) -> None:
    html = src.read_text()

    def repl(m: re.Match) -> str:
        name = m.group(1)
        path = next((p for p in (SHOTS / f"{name}.jpg", SHOTS / f"{name}.png") if p.exists()), None)
        if not path:
            raise SystemExit(f"missing screenshot: {name}")
        mime = "image/jpeg" if path.suffix == ".jpg" else "image/png"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"

    out.write_text(re.sub(r"\{\{img:([\w-]+)\}\}", repl, html))
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    for name in ("report", "slides"):
        embed(ROOT / "docs" / "src" / f"{name}.src.html", ROOT / "docs" / f"{name}.html")
