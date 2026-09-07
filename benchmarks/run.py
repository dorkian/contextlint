#!/usr/bin/env python3
"""Reproduce every number contextlint publishes.

    python benchmarks/run.py

Three measurements, all deterministic, all runnable by anyone who clones the repo:

1. **Detection** — audit the fixture workspace and confirm each planted defect is
   found. A savings claim from a tool that misses defects is worth nothing.
2. **Savings** — copy the fixture, run the real ``fix`` path against the copy, and
   re-audit. The reported percentage is the difference between two measured audits,
   not an estimate of what could be saved.
3. **Tokenizer error** — replayed from ``results/calibration.json`` when present;
   regenerate it with ``benchmarks/calibrate.py``.

The point of this file is that the README's numbers have a command attached. Every
comparable tool in this space publishes percentages with no reproduction path.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from contextlint.audit import run_audit  # noqa: E402
from contextlint.fix import apply_plan, build_plan  # noqa: E402

FIXTURE = REPO / "benchmarks" / "fixtures" / "bloated"

EXPECTED = [
    ("invisible characters", "critical"),
    ("plaintext credential in mcp config", "critical"),
    ("no configured auth", "high"),
    ("plaintext http", "high"),
    ("launches through a shell", "high"),
    ("scoped to /", "high"),
    ("blanket command permission", "high"),
    ("unpinned code", "medium"),
    ("byte-identical", "high"),
    ("defined 3 times", "medium"),
    ("effectively empty", "medium"),
    ("instruction override", "medium"),
    ("user concealment", "medium"),
    ("tool-order hijack", "medium"),
    ("credential exfiltration", "medium"),
]


def audit(path: Path):
    return run_audit(str(path), include_global=False, use_usage=False)


def detection(report) -> dict:
    titles = [(f.title.lower(), f.severity) for f in report.findings]
    rows = []
    for needle, severity in EXPECTED:
        hit = next((s for t, s in titles if needle in t), None)
        rows.append({"defect": needle, "expected": severity, "found": hit,
                     "ok": hit == severity})
    return {"total": len(rows), "passed": sum(r["ok"] for r in rows), "rows": rows}


def savings() -> dict:
    before = audit(FIXTURE)
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / "ws"
        shutil.copytree(FIXTURE, ws)
        plan = build_plan(audit(ws))
        removed, _ = apply_plan(plan, ws)
        shutil.rmtree(ws / ".contextlint-backups", ignore_errors=True)
        after = audit(ws)
    cut = before.always_on_tokens - after.always_on_tokens
    return {
        "always_on_before": before.always_on_tokens,
        "always_on_after": after.always_on_tokens,
        "tokens_removed": cut,
        "reduction_pct": round(cut / before.always_on_tokens * 100, 2) if before.always_on_tokens else 0,
        "files_removed": removed,
        "findings_before": len(before.findings),
        "findings_after": len(after.findings),
        "note": "Automatic fixes only — byte-identical duplicates and empty assets. "
                "Judgement-call findings are excluded on purpose; including them is how a "
                "modest, honest number becomes an implausible one.",
    }


def calibration() -> dict | None:
    p = Path(__file__).parent / "results" / "calibration.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())["summary"]


def main() -> int:
    det = detection(audit(FIXTURE))
    sav = savings()
    cal = calibration()

    print("1. DETECTION — planted defects in benchmarks/fixtures/bloated")
    for r in det["rows"]:
        mark = "ok  " if r["ok"] else "MISS"
        print(f"   {mark} {r['defect']:<36} expected {r['expected']:<8} got {r['found']}")
    print(f"   {det['passed']}/{det['total']} detected\n")

    print("2. SAVINGS — measured before/after, automatic fixes only")
    print(f"   always-on before   {sav['always_on_before']:,} tokens")
    print(f"   always-on after    {sav['always_on_after']:,} tokens")
    print(f"   reduction          {sav['reduction_pct']}%  ({sav['files_removed']} files removed)")
    print(f"   findings           {sav['findings_before']} -> {sav['findings_after']}\n")

    print("3. TOKENIZER ERROR — heuristic vs tiktoken o200k_base")
    if cal:
        print(f"   corpus             {cal['files']:,} files, {cal['true_tokens']:,} true tokens")
        print(f"   aggregate error    {cal['aggregate_error_pct']:+.2f}%")
        print(f"   median per-file    {cal['median_abs_error_pct']:.2f}%")
        print(f"   p90 per-file       {cal['p90_abs_error_pct']:.2f}%")
    else:
        print("   not measured yet — run:")
        print("     uv run --no-project --with tiktoken python benchmarks/calibrate.py")

    out = Path(__file__).parent / "results" / "benchmark.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"detection": det, "savings": sav, "calibration": cal}, indent=2))
    print(f"\nwritten to {out}")
    return 0 if det["passed"] == det["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
