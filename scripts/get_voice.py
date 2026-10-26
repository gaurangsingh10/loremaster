"""Download the optional Kokoro neural voice model (~340 MB) into models/ (gitignored).

    pip install -r requirements-voice.txt
    python scripts/get_voice.py

Source: https://github.com/thewh1teagle/kokoro-onnx (model files release v1.0, Apache-2.0 Kokoro-82M weights).
Without it, the app uses your computer's built-in voice (macOS/Windows) or the browser's voice.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {"kokoro-v1.0.onnx": 300_000_000, "voices-v1.0.bin": 25_000_000}


def main() -> None:
    out = ROOT / "models"
    out.mkdir(exist_ok=True)
    for name, min_size in FILES.items():
        dest = out / name
        if dest.exists() and dest.stat().st_size >= min_size:
            print(f"{name}: already downloaded")
            continue
        print(f"downloading {name} …", flush=True)
        urllib.request.urlretrieve(BASE + name, dest)
        if dest.stat().st_size < min_size:
            sys.exit(f"{name} looks incomplete; delete it and retry")
    print("done: restart the backend and the narrator will use the neural voice")


if __name__ == "__main__":
    main()
