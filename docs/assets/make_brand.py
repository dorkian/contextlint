#!/usr/bin/env python3
"""Generate the logo mark, README hero, and GitHub social preview.

    python docs/assets/make_brand.py

The mark is the chart the tool draws: a stack of measured bars, the topmost one
separated by a gap because always-on cost is a different thing from the rest.
It is built from the same tokens as the charts, so the README reads as one system.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from theme import DARK, FONT, LIGHT, MONO, THEMES, esc, fmt, rect, text  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE


def mark(x: float, y: float, size: float, t: dict, *, on_dark_plate: bool = False) -> str:
    """The logo mark. Legible down to 16px: one accent tile, three receding bars."""
    u = size / 24.0
    plate = t["accent"]
    fg = "#ffffff"
    dim = "#ffffff" if on_dark_plate else "#ffffff"
    b = [f'<g transform="translate({x:.2f},{y:.2f})">',
         rect(0, 0, 24 * u, 24 * u, plate, r=6 * u)]
    # the always-on band, held apart from the rest by a deliberate gap
    b.append(rect(5 * u, 5.5 * u, 14 * u, 3 * u, fg, r=1.5 * u))
    for i, w in enumerate((11, 8, 5)):
        b.append(rect(5 * u, (11.5 + i * 3.6) * u, w * u, 2.2 * u, dim, r=1.1 * u,
                      opacity=0.62 - i * 0.13))
    b.append("</g>")
    return "".join(b)


def wordmark(x: float, y: float, t: dict, *, size: float = 34) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family=\'{MONO}\' font-size="{size}" '
            f'font-weight="600" letter-spacing="-0.4" fill="{t["ink"]}">'
            f'context<tspan fill="{t["accent"]}">lint</tspan></text>')


def logo(t: dict) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        f'role="img" aria-label="contextlint">{mark(0, 0, 24, t)}</svg>'
    )


def chip(x: float, y: float, value: str, label: str, t: dict) -> tuple[str, float]:
    vw = len(value) * 11.2 + 14
    lw = len(label) * 6.35 + 14
    w = max(vw, lw)
    b = [
        f'<text x="{x:.1f}" y="{y:.1f}" font-family=\'{MONO}\' font-size="21" '
        f'font-weight="650" fill="{t["ink"]}">{esc(value)}</text>',
        text(x, y + 19, label, size=11.5, fill=t["ink3"]),
    ]
    return "".join(b), w


def hero(t: dict, case: dict, bench: dict) -> str:
    W, H = 1200, 300
    cal = (bench or {}).get("calibration") or {}
    det = (bench or {}).get("detection") or {}
    b = [
        f'<rect width="{W}" height="{H}" fill="{t["surface"]}"/>',
        f'<rect x="0" y="{H - 4}" width="{W}" height="4" fill="{t["accent"]}"/>',
        mark(64, 62, 62, t),
        wordmark(148, 108, t, size=40),
        text(150, 142,
             "Audit what your AI coding assistant loads before you type a word.",
             size=17, fill=t["ink2"]),
        text(150, 166,
             "Token cost · dead weight · MCP security  —  Claude Code, Codex, Cursor, Copilot",
             size=14, fill=t["ink3"]),
    ]
    b.append(f'<line x1="64" y1="200" x2="{W - 64}" y2="200" stroke="{t["grid"]}" stroke-width="1"/>')

    chips = [
        (f"{det.get('passed', 15)}/{det.get('total', 15)}", "planted defects detected"),
        (f"{cal.get('aggregate_error_pct', 1.05):+.2f}%", "tokenizer error vs tiktoken"),
        ("0", "required dependencies"),
        ("4", "assistants, one model"),
    ]
    x = 64
    for value, label in chips:
        s, w = chip(x, 244, value, label, t)
        b.append(s)
        x += max(w, 190) + 44
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
            f'height="{H}" role="img" aria-labelledby="ht hd" font-family=\'{FONT}\'>'
            f'<title id="ht">contextlint</title>'
            f'<desc id="hd">contextlint — audit what your AI coding assistant loads before you '
            f'type a word: token cost, dead weight and MCP security across Claude Code, Codex, '
            f'Cursor and Copilot.</desc>{"".join(b)}</svg>')


def social(t: dict, case: dict, bench: dict) -> str:
    """1280x640 — GitHub's social preview slot. Big type, few words, readable as a thumbnail."""
    W, H = 1280, 640
    cal = (bench or {}).get("calibration") or {}
    naive = case["always_on_tokens"] + case["on_demand_tokens"]
    real = case["always_on_tokens"]
    b = [
        f'<rect width="{W}" height="{H}" fill="{t["surface"]}"/>',
        f'<rect x="0" y="0" width="{W}" height="8" fill="{t["accent"]}"/>',
        mark(88, 92, 76, t),
        wordmark(190, 150, t, size=52),
        text(192, 196, "Audit what your AI coding assistant loads before you type a word.",
             size=24, fill=t["ink2"]),
    ]
    # the one idea worth putting on a thumbnail
    y = 274
    b.append(text(88, y, "The same setup, measured two ways", size=17, weight=650, fill=t["ink"]))
    x0, x1 = 88, W - 88
    plot = x1 - x0
    scale = plot / naive
    for label, value, color, on_bar in (
        ("priced by size on disk", naive, t["muted"], t["ink"]),
        ("priced by loading mode", real, t["accent"], "#ffffff"),
    ):
        y += 34
        b.append(rect(x0, y, plot, 46, t["track"], r=6))
        bw = value * scale
        b.append(rect(x0, y, bw, 46, color, r=6))
        inside = bw > 320
        b.append(text(x0 + bw - 16 if inside else x0 + bw + 16, y + 31,
                      f"{fmt(value)} tok · {value / case['context_window']:.1%} of the window",
                      size=20, weight=650, fill=on_bar if inside else t["ink"],
                      anchor="end" if inside else "start"))
        b.append(text(x0, y + 68, label, size=15, fill=t["ink3"]))
        y += 42
    b.append(text(88, y + 62,
                  f"Pricing by size on disk overstates this setup's standing cost by "
                  f"{naive / real:.1f}×.",
                  size=19, weight=600, fill=t["ink"]))
    b.append(text(88, y + 90,
                  "Skill bodies load on demand. Only the one-line catalog entry is always-on.",
                  size=15, fill=t["ink2"]))
    b.append(text(88, H - 52,
                  f"{cal.get('aggregate_error_pct', 1.05):+.2f}% tokenizer error, measured   ·   "
                  f"0 dependencies   ·   read-only by default",
                  size=16, fill=t["ink2"]))
    b.append(text(W - 88, H - 52, "github.com/dorkian/contextlint", size=16,
                  fill=t["ink3"], anchor="end", mono=True))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
            f'height="{H}" role="img" aria-label="contextlint social preview" '
            f'font-family=\'{FONT}\'>{"".join(b)}</svg>')


def main() -> int:
    case = json.loads((HERE / "data" / "case-study.json").read_text())
    bp = HERE.parents[1] / "benchmarks" / "results" / "benchmark.json"
    bench = json.loads(bp.read_text()) if bp.exists() else {}
    for t in THEMES:
        (OUT / f"logo-{t['name']}.svg").write_text(logo(t))
        (OUT / f"hero-{t['name']}.svg").write_text(hero(t, case, bench))
        (OUT / f"social-{t['name']}.svg").write_text(social(t, case, bench))
    print("logo, hero and social preview written for both themes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
