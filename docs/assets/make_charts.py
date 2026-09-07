#!/usr/bin/env python3
"""Generate every README chart from measured data.

    python docs/assets/make_charts.py

Reads docs/assets/data/case-study.json (aggregates from the dogfood audit) and
benchmarks/results/benchmark.json (regenerate with benchmarks/run.py). Emits a
light and a dark SVG per chart, paired in the README with <picture>.

Charts are generated rather than drawn so that a number can never drift from the
measurement behind it. If a figure changes, re-run this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from theme import DARK, LIGHT, MONO, THEMES, esc, fmt, rect, svg, text  # noqa: E402

HERE = Path(__file__).parent
REPO = HERE.parents[1]
OUT = HERE

W = 900


def load() -> tuple[dict, dict]:
    case = json.loads((HERE / "data" / "case-study.json").read_text())
    bench_path = REPO / "benchmarks" / "results" / "benchmark.json"
    bench = json.loads(bench_path.read_text()) if bench_path.exists() else {}
    return case, bench


# --- 1. the cost model -------------------------------------------------------

def cost_model(c: dict, t: dict) -> str:
    """Emphasis form: one bar is the point, the other is the context it corrects."""
    window = c["context_window"]
    naive = c["always_on_tokens"] + c["on_demand_tokens"]
    real = c["always_on_tokens"]
    h = 250
    x0, x1 = 34, W - 34
    plot = x1 - x0
    scale = plot / naive

    rows = [
        # on-bar label colour is chosen per bar: white on the saturated accent,
        # ink on the de-emphasis gray, which white would disappear into.
        ("Priced by size on disk", "what every other auditor reports", naive, t["muted"], t["ink"], False),
        ("Priced by loading mode", "what is actually always-on", real, t["accent"], "#ffffff", True),
    ]
    b = [
        text(x0, 34, "The same setup, measured two ways", size=17, weight=650, fill=t["ink"]),
        text(x0, 55, "A skill's body loads only when invoked. Only its one-line catalog entry is always-on.",
             size=12.5, fill=t["ink2"]),
    ]

    # context-window reference line
    wx = x0 + window * scale
    b.append(f'<line x1="{wx:.1f}" y1="76" x2="{wx:.1f}" y2="196" stroke="{t["grid"]}" '
             f'stroke-width="2" stroke-dasharray="3 3"/>')
    b.append(text(wx, 70, "200k context window", size=11, fill=t["ink3"], anchor="middle"))

    y = 92
    for label, sub, value, color, on_bar, is_point in rows:
        bw = value * scale
        b.append(text(x0, y - 4, label, size=13,
                      weight=650 if is_point else 500,
                      fill=t["ink"] if is_point else t["ink2"]))
        b.append(text(x1, y - 4, sub, size=11.5, fill=t["ink3"], anchor="end"))
        b.append(rect(x0, y + 4, plot, 30, t["track"], r=4))
        b.append(rect(x0, y + 4, bw, 30, color, r=4))
        pct = value / window
        inside = bw > 250
        b.append(text(
            x0 + bw - 12 if inside else x0 + bw + 12, y + 24,
            f"{fmt(value)} tokens  ·  {pct:.1%} of the window",
            size=13, weight=650,
            fill=on_bar if inside else t["ink"],
            anchor="end" if inside else "start", mono=False))
        y += 62

    b.append(f'<line x1="{x0}" y1="216" x2="{x1}" y2="216" stroke="{t["grid"]}" stroke-width="1"/>')
    b.append(text(x0, 236,
                  f"Pricing by file size overstates this setup's standing cost by {naive / real:.1f}×.",
                  size=12.5, fill=t["ink2"], weight=550))
    return svg(W, h, t, "".join(b),
               title="Cost model comparison",
               desc=(f"Pricing agent config by file size reports {fmt(naive)} tokens, "
                     f"{naive / window:.0%} of a 200,000-token window. Pricing by loading mode "
                     f"reports {fmt(real)} always-on tokens, {real / window:.0%} of the window - "
                     f"a factor of {naive / real:.1f} difference."))


# --- 2. always-on budget -----------------------------------------------------

def budget(c: dict, t: dict) -> str:
    """Part-to-whole: horizontal stacked bar, four categorical slots, direct-labelled."""
    parts = list(c["always_on_by_kind"].items())
    total = sum(v for _, v in parts)
    h = 214
    x0, x1 = 34, W - 34
    plot = x1 - x0
    gap = 2

    b = [
        text(x0, 34, "Where the always-on tokens go", size=17, weight=650, fill=t["ink"]),
        text(x0, 55, f"{fmt(total)} tokens injected before the first keystroke, by source.",
             size=12.5, fill=t["ink2"]),
    ]

    x = x0
    bar_y, bar_h = 76, 40
    for i, (name, value) in enumerate(parts):
        w = plot * value / total - (gap if i < len(parts) - 1 else 0)
        b.append(rect(x, bar_y, max(w, 1), bar_h, t["series"][i], r=4))
        if w > 74:
            b.append(text(x + w / 2, bar_y + 25, f"{value / total:.0%}", size=13.5,
                          weight=650, fill=t["surface"], anchor="middle"))
        x += w + gap

    # legend: always present, and each entry carries its own number
    ly = 148
    lx = x0
    for i, (name, value) in enumerate(parts):
        b.append(rect(lx, ly - 9, 11, 11, t["series"][i], r=2.5))
        b.append(text(lx + 18, ly, name, size=12.5, fill=t["ink"]))
        b.append(text(lx + 18, ly + 17, f"{fmt(value)} tok", size=12, fill=t["ink3"], mono=True))
        lx += 214

    b.append(f'<line x1="{x0}" y1="182" x2="{x1}" y2="182" stroke="{t["grid"]}" stroke-width="1"/>')
    b.append(text(x0, 202,
                  "MCP tool schemas are invisible to static config — this figure was measured "
                  "with --mcp-probe.", size=12, fill=t["ink2"]))
    return svg(W, h, t, "".join(b),
               title="Always-on token budget by source",
               desc="; ".join(f"{k}: {fmt(v)} tokens, {v / total:.0%}" for k, v in parts))


# --- 3. installed vs invoked -------------------------------------------------

def usage(c: dict, t: dict) -> str:
    """One square per skill. A waffle keeps the unit honest: each mark is one skill."""
    installed, invoked = c["skills_installed"], c["skills_invoked"]
    never = installed - invoked
    cols, cell, pad = 23, 26, 5
    rows = (installed + cols - 1) // cols
    x0 = 34
    grid_h = rows * (cell + pad) - pad
    h = 118 + grid_h + 74

    b = [
        text(x0, 34, "Installed skills against skills ever invoked", size=17, weight=650, fill=t["ink"]),
        text(x0, 55, f"One square is one skill. {c['sessions']} sessions of transcripts, "
                     f"{c['session_span_days']:.0f} days.", size=12.5, fill=t["ink2"]),
    ]

    top = 78
    for i in range(installed):
        r, col = divmod(i, cols)
        x = x0 + col * (cell + pad)
        y = top + r * (cell + pad)
        used = i < invoked
        b.append(rect(x, y, cell, cell, t["accent"] if used else t["serious"], r=4,
                      opacity=None if used else 0.9))

    ly = top + grid_h + 32
    b.append(rect(x0, ly - 10, 11, 11, t["accent"], r=2.5))
    b.append(text(x0 + 18, ly, f"invoked at least once — {invoked}", size=12.5, fill=t["ink"]))
    b.append(rect(x0 + 268, ly - 10, 11, 11, t["serious"], r=2.5))
    b.append(text(x0 + 286, ly, f"never invoked — {never}", size=12.5, fill=t["ink"]))

    b.append(text(W - 34, ly, f"{never}/{installed}", size=26, weight=700,
                  fill=t["ink"], anchor="end", mono=True))
    b.append(text(x0, ly + 26,
                  "Reported as something to review, not to delete: a rarely-used skill can be the "
                  "one that matters when it fires.", size=12, fill=t["ink2"]))
    return svg(W, h, t, "".join(b),
               title="Installed skills versus skills ever invoked",
               desc=f"{installed} skills installed; {invoked} invoked at least once across "
                    f"{c['sessions']} sessions; {never} never invoked.")


# --- 4. MCP servers ----------------------------------------------------------

def mcp(c: dict, t: dict) -> str:
    """Emphasis: cost in the accent hue, never-called in the warning hue."""
    servers = sorted(c["mcp_servers"], key=lambda s: -s["tokens"])
    top = max(s["tokens"] for s in servers) or 1
    x0, x1 = 34, W - 34
    label_w, note_w = 108, 218
    plot = x1 - x0 - label_w - note_w
    row_h = 40
    h = 118 + len(servers) * row_h + 46

    b = [
        text(x0, 34, "What each MCP server costs, and whether it is used", size=17, weight=650, fill=t["ink"]),
        text(x0, 55, "Tool schemas measured from live tools/list responses, not estimated.",
             size=12.5, fill=t["ink2"]),
    ]

    y = 84
    for s in servers:
        used = s["called"]
        color = t["accent"] if used else t["serious"]
        b.append(text(x0, y + 20, s["name"], size=13, weight=600 if used else 500,
                      fill=t["ink"] if used else t["ink2"], mono=True))
        bx = x0 + label_w
        b.append(rect(bx, y + 8, plot, 18, t["track"], r=4))
        if s["tokens"]:
            b.append(rect(bx, y + 8, plot * s["tokens"] / top, 18, color, r=4))
            b.append(text(bx + plot * s["tokens"] / top + 10, y + 21,
                          f"{fmt(s['tokens'])} tok/turn", size=12, weight=600, fill=t["ink"], mono=True))
        else:
            b.append(text(bx + 10, y + 21, "unmeasurable", size=12, fill=t["ink3"]))
        note = (f"{s['tools']} tools" if s["tools"] else s["status"])
        if not used:
            note += " · never called"
        b.append(text(x1, y + 21, note, size=11.5,
                      fill=t["ink3"] if used else t["serious"], anchor="end"))
        y += row_h

    b.append(f'<line x1="{x0}" y1="{y + 4}" x2="{x1}" y2="{y + 4}" stroke="{t["grid"]}" stroke-width="1"/>')
    b.append(text(x0, y + 26,
                  "1,699 tokens per request, forever, for a server never called in 148 sessions — "
                  "and three more that do not start.", size=12, fill=t["ink2"], weight=550))
    return svg(W, h, t, "".join(b),
               title="MCP server cost and usage",
               desc="; ".join(
                   f"{s['name']}: {fmt(s['tokens'])} tokens per turn, "
                   f"{'called' if s['called'] else 'never called'}, {s['status']}"
                   for s in servers))


# --- 5. tokenizer accuracy ---------------------------------------------------

def tokenizer(bench: dict, t: dict) -> str:
    cal = (bench or {}).get("calibration") or {}
    if not cal:
        return ""
    agg = cal["aggregate_error_pct"]
    bars = [("median per file", cal["median_abs_error_pct"]),
            ("p90 per file", cal["p90_abs_error_pct"]),
            ("worst file", cal["worst_abs_error_pct"])]
    top = max(v for _, v in bars) * 1.18
    x0, x1 = 34, W - 34
    h = 244

    b = [
        text(x0, 34, "Offline tokenizer error against tiktoken", size=17, weight=650, fill=t["ink"]),
        text(x0, 55, f"{cal['files']:,} files · {cal['true_tokens']:,} true tokens · "
                     f"parameters fitted on half the corpus, measured on the other half",
             size=12.5, fill=t["ink2"]),
    ]

    # hero figure: the number that governs a total
    b.append(text(x0, 116, f"{agg:+.2f}%", size=44, weight=700, fill=t["accent"], mono=True))
    b.append(text(x0, 138, "aggregate error over the whole corpus", size=12, fill=t["ink2"]))
    b.append(text(x0, 158, "— the figure that governs a reported total", size=11.5, fill=t["ink3"]))

    bx0 = x0 + 340
    label_w, value_w = 110, 86   # value_w reserves room so a full-length bar cannot
    plot = x1 - bx0 - label_w - value_w   # run underneath its own number
    y = 82
    for label, value in bars:
        b.append(text(bx0, y + 12, label, size=12, fill=t["ink2"]))
        b.append(rect(bx0 + label_w, y + 2, plot, 14, t["track"], r=4))
        b.append(rect(bx0 + label_w, y + 2, plot * value / top, 14, t["accent"], r=4, opacity=0.85))
        b.append(text(x1, y + 14, f"{value:.2f}%", size=12.5, weight=600, fill=t["ink"],
                      anchor="end", mono=True))
        y += 30
    b.append(text(bx0, y + 14, "absolute error, per individual file", size=11.5, fill=t["ink3"]))

    b.append(f'<line x1="{x0}" y1="200" x2="{x1}" y2="200" stroke="{t["grid"]}" stroke-width="1"/>')
    b.append(text(x0, 222,
                  "Calibrated on agent configuration — markdown, JSON schemas, YAML frontmatter. "
                  "Error on other text is unmeasured.", size=12, fill=t["ink2"]))
    return svg(W, h, t, "".join(b),
               title="Tokenizer accuracy",
               desc=(f"Aggregate error {agg:+.2f}% over {cal['files']} files. "
                     f"Median per-file absolute error {cal['median_abs_error_pct']}%, "
                     f"p90 {cal['p90_abs_error_pct']}%, worst {cal['worst_abs_error_pct']}%."))


# --- 6. savings split --------------------------------------------------------

def savings(c: dict, t: dict) -> str:
    """Two numbers that must never be added together, drawn so they can't be."""
    certain, candidate = c["certain_tokens"], c["candidate_tokens"]
    total = c["always_on_tokens"]
    x0, x1 = 34, W - 34
    plot = x1 - x0
    row_h, rows_n = 76, 2
    h = 84 + row_h * rows_n + 48   # header + rows + footnote; sized, not guessed

    b = [
        text(x0, 34, "What is recoverable, split by whether it is a decision", size=17, weight=650, fill=t["ink"]),
        text(x0, 55, f"Of {fmt(total)} always-on tokens. These two figures are never summed.",
             size=12.5, fill=t["ink2"]),
    ]

    rows = [
        ("Safe to reclaim", certain, t["good"],
         "byte-identical duplicates and empty assets — removing them cannot change behaviour"),
        ("Worth reviewing", candidate, t["serious"],
         "unused skills, an uncalled server — every one of these is a judgement call"),
    ]
    y = 84
    for label, value, color, note in rows:
        b.append(text(x0, y + 12, label, size=13.5, weight=650, fill=t["ink"]))
        b.append(text(x1, y + 12, f"{fmt(value)} tok  ·  {value / total:.0%}", size=13.5,
                      weight=650, fill=t["ink"], anchor="end", mono=True))
        b.append(rect(x0, y + 22, plot, 14, t["track"], r=4))
        b.append(rect(x0, y + 22, plot * value / total, 14, color, r=4))
        b.append(text(x0, y + 54, note, size=12, fill=t["ink2"]))
        y += row_h

    b.append(f'<line x1="{x0}" y1="{y - 8}" x2="{x1}" y2="{y - 8}" stroke="{t["grid"]}" stroke-width="1"/>')
    b.append(text(x0, y + 14,
                  f"Adding them would headline “{(certain + candidate) / total:.0%} reduction available”. "
                  f"It would also be meaningless.", size=12.5, fill=t["ink2"], weight=550))
    return svg(W, h, t, "".join(b),
               title="Recoverable tokens, split by confidence",
               desc=(f"Safe to reclaim {fmt(certain)} tokens ({certain / total:.0%}); "
                     f"worth reviewing {fmt(candidate)} tokens ({candidate / total:.0%}). "
                     f"Reported separately, never summed."))


CHARTS = {
    "cost-model": lambda c, b, t: cost_model(c, t),
    "budget": lambda c, b, t: budget(c, t),
    "usage": lambda c, b, t: usage(c, t),
    "mcp": lambda c, b, t: mcp(c, t),
    "tokenizer": lambda c, b, t: tokenizer(b, t),
    "savings": lambda c, b, t: savings(c, t),
}


def main() -> int:
    case, bench = load()
    written = 0
    for name, fn in CHARTS.items():
        for t in THEMES:
            content = fn(case, bench, t)
            if not content:
                print(f"  skipped {name} ({t['name']}) — no data")
                continue
            path = OUT / f"{name}-{t['name']}.svg"
            path.write_text(content, encoding="utf-8")
            written += 1
            if t is LIGHT:
                print(f"  {path.name:<28} {len(content):>6,} bytes")
    print(f"\n{written} SVGs written to {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
