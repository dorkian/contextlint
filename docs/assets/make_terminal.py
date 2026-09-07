#!/usr/bin/env python3
"""Render a real CLI run as an SVG terminal window.

    python docs/assets/make_terminal.py

Runs contextlint for real and renders exactly what it printed. Home paths are
shortened to `~` and nothing else is edited — a README screenshot that does not
match what the tool actually outputs is a lie with a picture attached.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from theme import DARK, LIGHT, MONO, THEMES, esc  # noqa: E402

HERE = Path(__file__).parent
REPO = HERE.parents[1]
TARGET = REPO / "benchmarks" / "fixtures" / "bloated"

CH_W, LINE_H, PAD_X, PAD_Y, CHROME = 7.22, 19.0, 22, 20, 38
FONT_SIZE = 12.4


def capture() -> list[str]:
    env = {**os.environ, "NO_COLOR": "1", "PYTHONPATH": str(REPO / "src"),
           "COLUMNS": "104"}
    out = subprocess.run(
        [sys.executable, "-m", "contextlint", "audit", str(TARGET),
         "--no-global", "--no-usage", "--max-findings", "4"],
        capture_output=True, text=True, env=env, cwd=REPO, check=False,
    ).stdout
    # repo path first: shortening home first would stop the repo path from matching
    out = out.replace(str(REPO), "~/contextlint").replace(str(Path.home()), "~")
    return out.splitlines()


SEV = re.compile(r"^\s*(CRIT|HIGH|MED|LOW|INFO)\b")
HEAD = re.compile(r"^(ALWAYS-ON CONTEXT|WHERE IT GOES|FINDINGS|REAL USAGE)")


def colorise(line: str, t: dict) -> tuple[str, str, int]:
    """Return (fill, weight, indent-preserving text). Colour follows meaning only."""
    tone = {
        "CRIT": t["critical"], "HIGH": t["critical"], "MED": t["series"][3],
        "LOW": t["series"][0], "INFO": t["ink3"],
    }
    m = SEV.match(line)
    if m:
        return tone[m.group(1)], "600", 0
    if HEAD.match(line):
        return t["ink"], "700", 0
    if line.startswith("  →") or line.strip().startswith("→"):
        return t["series"][2], "400", 0
    if "█" in line or "▉" in line:
        return t["accent"], "400", 0
    if line.startswith("contextlint"):
        return t["ink"], "700", 0
    if line.startswith("       ") or line.startswith("─"):
        return t["ink3"], "400", 0
    return t["ink2"], "400", 0


def render(lines: list[str], t: dict) -> str:
    width = int(max(len(l) for l in lines) * CH_W) + PAD_X * 2
    height = CHROME + PAD_Y + len(lines) * LINE_H + PAD_Y
    bg = "#111110" if t is DARK else "#1c1c1a"
    ink = {**t, "ink": "#f2f1ea", "ink2": "#c8c6bc", "ink3": "#8a8880",
           "accent": "#5c9dee", "critical": "#ff8b8b",
           "series": ["#5c9dee", "#e0955f", "#6fbf92", "#e8c46a"]}

    b = [f'<rect width="{width}" height="{height}" fill="{bg}" rx="10"/>',
         f'<rect width="{width}" height="{CHROME}" fill="#000000" opacity="0.22"/>']
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        b.append(f'<circle cx="{22 + i * 19}" cy="{CHROME / 2}" r="5.5" fill="{c}"/>')
    b.append(
        f'<text x="{width / 2}" y="{CHROME / 2 + 4}" font-family=\'{MONO}\' font-size="11" '
        f'fill="#8a8880" text-anchor="middle">contextlint — audit</text>')

    y = CHROME + PAD_Y + 12
    for line in lines:
        if line.strip():
            fill, weight, _ = colorise(line, ink)
            b.append(
                f'<text x="{PAD_X}" y="{y:.1f}" font-family=\'{MONO}\' font-size="{FONT_SIZE}" '
                f'font-weight="{weight}" fill="{fill}" xml:space="preserve">{esc(line)}</text>')
        y += LINE_H

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" aria-label="Terminal output of '
            f'contextlint audit against the bundled fixture workspace">{"".join(b)}</svg>')


def main() -> int:
    lines = capture()
    if not lines:
        print("no output captured", file=sys.stderr)
        return 1
    (HERE / "terminal.svg").write_text(render(lines, DARK), encoding="utf-8")
    print(f"terminal.svg written — {len(lines)} lines, "
          f"{max(len(l) for l in lines)} cols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
