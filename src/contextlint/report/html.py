"""A single self-contained HTML file: treemap, usage-vs-cost scatter, findings.

No CDN, no build step, no fonts fetched over the network — the output is one file
you can email, attach to a ticket, or open on a plane. A tool that audits what
your assistant loads should not itself pull 300 KB of JavaScript to draw a box.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from ..models import CERTAIN, CRITICAL, HIGH, INFO, LOW, MEDIUM, Report

SEV_TONE = {CRITICAL: "crit", HIGH: "high", MEDIUM: "med", LOW: "low", INFO: "info"}


# --- squarified treemap ------------------------------------------------------

def _squarify(values: list[float], x: float, y: float, w: float, h: float) -> list[tuple[float, float, float, float]]:
    """Bruls/Huizing/van Wijk squarified layout. Values must be sorted descending."""
    rects: list[tuple[float, float, float, float]] = []
    items = list(values)
    total = sum(items) or 1.0
    scale = (w * h) / total
    items = [v * scale for v in items]

    while items:
        row: list[float] = []
        short = min(w, h)
        while items:
            trial = row + [items[0]]
            if row and _worst(trial, short) > _worst(row, short):
                break
            row.append(items.pop(0))
        row_sum = sum(row) or 1.0
        if w >= h:
            rw = row_sum / h
            oy = y
            for v in row:
                rh = v / rw if rw else 0
                rects.append((x, oy, rw, rh))
                oy += rh
            x += rw
            w -= rw
        else:
            rh = row_sum / w
            ox = x
            for v in row:
                rw = v / rh if rh else 0
                rects.append((ox, y, rw, rh))
                ox += rw
            y += rh
            h -= rh
    return rects


def _worst(row: list[float], length: float) -> float:
    s = sum(row) or 1e-9
    mx, mn = max(row), min(row)
    return max((length ** 2) * mx / (s ** 2), (s ** 2) / ((length ** 2) * mn)) if mn else float("inf")


def _treemap_svg(report: Report, usage: dict, width: int = 920, height: int = 380) -> str:
    assets = sorted(
        (a for a in report.assets if a.always_on_tokens > 0),
        key=lambda a: -a.always_on_tokens,
    )[:80]
    if not assets:
        return '<p class="empty">No always-on assets found.</p>'

    rects = _squarify([float(a.always_on_tokens) for a in assets], 0, 0, width, height)
    invoked = set((usage.get("skills") or {}).keys())
    total = report.always_on_tokens or 1

    parts = [f'<svg viewBox="0 0 {width} {height}" class="treemap" role="img" '
             f'aria-label="Always-on token cost by asset">']
    for a, (x, y, w, h) in zip(assets, rects):
        if w < 1 or h < 1:
            continue
        if a.kind in ("skill", "agent", "command"):
            tone = "used" if a.name in invoked else "unused"
        elif a.kind == "mcp_server":
            tone = "mcp"
        else:
            tone = "memory"
        share = a.always_on_tokens / total
        title = (f"{a.name}\n{a.assistant} / {a.kind}\n{a.always_on_tokens:,} always-on tokens "
                 f"({share:.1%})\nloading: {a.loading}")
        parts.append(
            f'<g class="cell {tone}"><title>{html.escape(title)}</title>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w - 1.5, 0):.1f}" '
            f'height="{max(h - 1.5, 0):.1f}" rx="2"/>'
        )
        if w > 58 and h > 20:
            label = a.name if len(a.name) < int(w / 6.6) else a.name[: max(int(w / 6.6) - 1, 3)] + "…"
            parts.append(f'<text x="{x + 6:.1f}" y="{y + 15:.1f}">{html.escape(label)}</text>')
            if h > 34:
                parts.append(
                    f'<text class="sub" x="{x + 6:.1f}" y="{y + 28:.1f}">{a.always_on_tokens:,}</text>'
                )
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


# --- usage vs cost scatter ---------------------------------------------------

def _scatter_svg(report: Report, usage: dict, width: int = 920, height: int = 300) -> str:
    skills = [a for a in report.assets if a.kind in ("skill", "agent", "command")]
    if not skills or not usage.get("available"):
        return ('<p class="empty">No session history available, so cost cannot be plotted against '
                'real usage. Run on a machine with agent transcripts present.</p>')

    stats = usage.get("skills") or {}
    pts = [(a, int((stats.get(a.name) or {}).get("count", 0))) for a in skills]
    max_uses = max((c for _, c in pts), default=1) or 1
    max_cost = max((a.always_on_tokens for a, _ in pts), default=1) or 1
    pad_l, pad_b, pad_t, pad_r = 54, 38, 16, 16
    pw, ph = width - pad_l - pad_r, height - pad_b - pad_t

    def px(c: int) -> float:
        return pad_l + (c ** 0.5 / max_uses ** 0.5) * pw

    def py(t: int) -> float:
        return pad_t + ph - (t / max_cost) * ph

    parts = [f'<svg viewBox="0 0 {width} {height}" class="scatter" role="img" '
             f'aria-label="Always-on cost plotted against real invocation count">']
    for i in range(5):
        gy = pad_t + ph * i / 4
        parts.append(f'<line class="grid" x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}"/>')
        parts.append(f'<text class="axis" x="6" y="{gy + 4:.1f}">{int(max_cost * (1 - i / 4)):,}</text>')
    parts.append(f'<text class="axis" x="{pad_l}" y="{height - 10}">never used</text>')
    parts.append(f'<text class="axis" text-anchor="end" x="{width - pad_r}" y="{height - 10}">'
                 f'{max_uses} invocations</text>')
    parts.append(f'<text class="axis" x="6" y="{pad_t - 4}">tokens</text>')

    for a, count in sorted(pts, key=lambda p: -p[0].always_on_tokens):
        r = 3.5 + min(a.always_on_tokens / max_cost, 1) * 5
        tone = "unused" if count == 0 else "used"
        title = f"{a.name}\n{a.always_on_tokens:,} always-on tokens\n{count} invocation(s)"
        parts.append(
            f'<g class="pt {tone}"><title>{html.escape(title)}</title>'
            f'<circle cx="{px(count):.1f}" cy="{py(a.always_on_tokens):.1f}" r="{r:.1f}"/></g>'
        )
    parts.append("</svg>")
    return "".join(parts)


# --- dependency edges --------------------------------------------------------

def _dependencies(report: Report) -> list[dict]:
    return report.dependencies()


# --- page --------------------------------------------------------------------

def write_html(report: Report, path: Path) -> Path:
    m = report.meta
    usage = m.get("usage") or {}
    total = report.always_on_tokens
    window = m["policy"]["context_window"]
    findings = [
        {
            "sev": f.severity, "tone": SEV_TONE[f.severity], "title": f.title, "detail": f.detail,
            "fix": f.remediation, "check": f.check, "tokens": f.tokens_at_stake,
            "path": str(f.path) if f.path else "", "certain": f.confidence == CERTAIN,
        }
        for f in report.sorted_findings()
    ]
    counts = report.counts_by_severity()
    deps = _dependencies(report)

    stat_cards = "".join(
        f'<div class="stat"><div class="k">{html.escape(k)}</div><div class="v">{html.escape(v)}</div></div>'
        for k, v in [
            ("always-on tokens", f"{total:,}"),
            ("share of window", f"{total / window:.1%}" if window else "—"),
            ("safe to reclaim", f"{report.certain_tokens:,}"),
            ("worth reviewing", f"{report.candidate_tokens:,}"),
            ("assets", f"{len(report.assets):,}"),
            ("sessions read", f"{usage.get('sessions', 0):,}"),
            ("findings", f"{len(findings):,}"),
        ]
    )

    dep_rows = "".join(
        f'<tr><td>{html.escape(d["skill"])}</td><td>{html.escape(", ".join(d["servers"]))}</td>'
        f'<td class="num">{d["tokens"]:,}</td></tr>'
        for d in deps[:25]
    ) or '<tr><td colspan="3" class="empty">No skill references an MCP server by name.</td></tr>'

    caveats = []
    if not m["tokenizer_exact"]:
        caveats.append(
            f"Token counts come from contextlint's offline heuristic (<code>{html.escape(m['tokenizer'])}</code>), "
            "not a real tokenizer. The measured error is published in <code>benchmarks/</code>."
        )
    if not m["mcp_probed"] and any(a.kind == "mcp_server" for a in report.assets):
        caveats.append(
            "MCP tool-schema cost is <strong>not included</strong> in these totals. Configuration "
            "cannot reveal it; re-run with <code>--mcp-probe</code> to measure it from live servers."
        )
    if not usage.get("available"):
        caveats.append("No session history was found, so nothing here distinguishes an unused asset "
                       "from a heavily used one.")
    caveat_html = "".join(f"<li>{c}</li>" for c in caveats) or "<li>None — every number here was measured.</li>"

    doc = _TEMPLATE.format(
        project=html.escape(m["project"]),
        generated=html.escape(str(m.get("generated_at", ""))),
        version=html.escape(m["version"]),
        assistants=html.escape(", ".join(m["assistants_detected"]) or "none"),
        stats=stat_cards,
        treemap=_treemap_svg(report, usage),
        scatter=_scatter_svg(report, usage),
        dep_rows=dep_rows,
        caveats=caveat_html,
        counts=json.dumps(counts),
        findings=json.dumps(findings),
    )
    path.write_text(doc, encoding="utf-8")
    return path


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>contextlint — {project}</title>
<style>
:root {{
  color-scheme: light dark;
  --bg:#fbfbfa; --panel:#fff; --ink:#16150f; --mute:#6b6a63; --line:#e6e4dd;
  --used:#3d7a5a; --unused:#c2703f; --mcp:#4a6fa5; --memory:#8a7bb8;
  --crit:#8f2020; --high:#b4471f; --med:#9a7415; --low:#4a6fa5; --info:#6b6a63;
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#14140f; --panel:#1c1c17; --ink:#eceae1; --mute:#9a978c; --line:#2f2f28;
    --used:#6fbf92; --unused:#e0955f; --mcp:#7fa3d6; --memory:#b3a3e0;
    --crit:#ff8b8b; --high:#ffab7d; --med:#e8c46a; --low:#9dc0f0; --info:#9a978c; }}
}}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:14px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.wrap {{ max-width:1000px; margin:0 auto; padding:40px 24px 80px }}
h1 {{ font-size:22px; margin:0 0 4px; letter-spacing:-.01em }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.09em; color:var(--mute);
  margin:40px 0 12px; font-weight:600 }}
.sub {{ color:var(--mute); font-size:13px }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:8px; overflow:hidden; margin-top:24px }}
.stat {{ background:var(--panel); padding:14px 16px }}
.stat .k {{ font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--mute) }}
.stat .v {{ font-size:22px; font-variant-numeric:tabular-nums; margin-top:2px }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; overflow-x:auto }}
svg {{ display:block; width:100%; height:auto; min-width:640px }}
.treemap .cell rect {{ stroke:var(--panel); stroke-width:1.5 }}
.treemap .used rect {{ fill:var(--used) }} .treemap .unused rect {{ fill:var(--unused) }}
.treemap .mcp rect {{ fill:var(--mcp) }} .treemap .memory rect {{ fill:var(--memory) }}
.treemap text {{ fill:#fff; font-size:11px; font-weight:600; pointer-events:none }}
.treemap text.sub {{ font-weight:400; opacity:.8; font-size:10px }}
.scatter .grid {{ stroke:var(--line) }}
.scatter .axis {{ fill:var(--mute); font-size:10px }}
.scatter .used circle {{ fill:var(--used); opacity:.75 }}
.scatter .unused circle {{ fill:var(--unused); opacity:.8 }}
.legend {{ display:flex; gap:18px; flex-wrap:wrap; margin-top:10px; font-size:12px; color:var(--mute) }}
.legend i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px }}
table {{ width:100%; border-collapse:collapse; font-size:13px }}
th,td {{ text-align:left; padding:7px 10px; border-bottom:1px solid var(--line) }}
th {{ font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--mute) }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums }}
.filters {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px }}
.filters button {{ font:inherit; font-size:12px; padding:5px 11px; border-radius:99px; cursor:pointer;
  border:1px solid var(--line); background:var(--panel); color:var(--mute) }}
.filters button[aria-pressed=true] {{ background:var(--ink); color:var(--bg); border-color:var(--ink) }}
.f {{ background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--line);
  border-radius:6px; padding:12px 14px; margin-bottom:8px }}
.f.crit {{ border-left-color:var(--crit) }} .f.high {{ border-left-color:var(--high) }}
.f.med {{ border-left-color:var(--med) }} .f.low {{ border-left-color:var(--low) }}
.f.info {{ border-left-color:var(--info) }}
.f .top {{ display:flex; gap:10px; align-items:baseline; flex-wrap:wrap }}
.f .sev {{ font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase }}
.f.crit .sev {{ color:var(--crit) }} .f.high .sev {{ color:var(--high) }}
.f.med .sev {{ color:var(--med) }} .f.low .sev {{ color:var(--low) }} .f.info .sev {{ color:var(--info) }}
.f .conf {{ font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
  color:var(--ok,#1baf7a); border:1px solid currentColor; border-radius:99px; padding:1px 7px }}
.f .t {{ font-weight:600; flex:1; min-width:200px }}
.f .cost {{ font-size:12px; color:var(--mute); font-variant-numeric:tabular-nums }}
.f .d {{ color:var(--mute); margin-top:6px; white-space:pre-wrap }}
.f .r {{ margin-top:6px }}
.f .p {{ font-size:11px; color:var(--mute); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; margin-top:6px }}
.caveats {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 18px }}
.caveats li {{ margin:6px 0; color:var(--mute) }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em }}
.empty {{ color:var(--mute); padding:12px 0 }}
footer {{ margin-top:48px; padding-top:16px; border-top:1px solid var(--line); color:var(--mute); font-size:12px }}
</style></head><body><div class="wrap">

<h1>contextlint</h1>
<div class="sub">{project} · assistants detected: {assistants} · contextlint {version}</div>
<div class="stats">{stats}</div>

<h2>Always-on cost by asset</h2>
<div class="card">{treemap}</div>
<div class="legend">
  <span><i style="background:var(--used)"></i>skill, used</span>
  <span><i style="background:var(--unused)"></i>skill, never invoked</span>
  <span><i style="background:var(--mcp)"></i>MCP server</span>
  <span><i style="background:var(--memory)"></i>memory / instructions</span>
</div>
<div class="sub" style="margin-top:8px">Area is always-on token cost. This is what you pay on every
request before typing a word — not the size of the file on disk.</div>

<h2>Cost against real usage</h2>
<div class="card">{scatter}</div>
<div class="sub" style="margin-top:8px">Anything high and to the left costs you on every request and
has never once been invoked. Horizontal axis is square-root scaled.</div>

<h2>Skills that reference an MCP server</h2>
<div class="card"><table><thead><tr><th>Skill</th><th>Servers</th><th class="num">Always-on tokens</th></tr></thead>
<tbody>{dep_rows}</tbody></table></div>

<h2>Findings</h2>
<p class="sub" style="margin:-6px 0 14px">A <span class="conf" style="display:inline-block">certain</span> badge means removing it cannot change behaviour (a byte-identical duplicate, an empty asset). Everything unmarked is a judgement call — contextlint reports it, it does not decide for you.</p>
<div class="filters" id="filters"></div>
<div id="findings"></div>

<h2>What this report does not know</h2>
<div class="caveats"><ul>{caveats}</ul></div>

<footer>Generated by contextlint. Every number above is reproducible from this machine's
configuration and transcripts; nothing was sent anywhere.</footer>
</div>
<script>
const FINDINGS = {findings}, COUNTS = {counts};
const order = ["all","critical","high","medium","low","info"];
let active = "all";
const fEl = document.getElementById("findings"), filtEl = document.getElementById("filters");
function esc(s) {{ const d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }}
function render() {{
  const list = active === "all" ? FINDINGS : FINDINGS.filter(f => f.sev === active);
  fEl.innerHTML = list.length ? list.map(f => `
    <div class="f ${{f.tone}}">
      <div class="top"><span class="sev">${{esc(f.sev)}}</span>
      ${{f.certain ? `<span class="conf" title="Removing this cannot change behaviour">certain</span>` : ""}}
      <span class="t">${{esc(f.title)}}</span>
      ${{f.tokens ? `<span class="cost">−${{f.tokens.toLocaleString()}} tok</span>` : ""}}</div>
      <div class="d">${{esc(f.detail)}}</div>
      ${{f.fix ? `<div class="r">→ ${{esc(f.fix)}}</div>` : ""}}
      ${{f.path ? `<div class="p">${{esc(f.path)}}</div>` : ""}}
    </div>`).join("") : '<p class="empty">Nothing at this severity.</p>';
  [...filtEl.children].forEach(b => b.setAttribute("aria-pressed", b.dataset.sev === active));
}}
filtEl.innerHTML = order.map(s => {{
  const n = s === "all" ? FINDINGS.length : (COUNTS[s] || 0);
  return `<button data-sev="${{s}}" aria-pressed="false">${{s}} ${{n}}</button>`;
}}).join("");
filtEl.addEventListener("click", e => {{
  const b = e.target.closest("button"); if (!b) return; active = b.dataset.sev; render();
}});
render();
</script></body></html>
"""
