#!/usr/bin/env python3
"""Measure the heuristic tokenizer's error against a real BPE tokenizer.

Run this before quoting any accuracy number anywhere. It is the reason contextlint
can say "within X%" instead of "approximately".

    uv run --with tiktoken benchmarks/calibrate.py [corpus_dir ...]

Corpus defaults to this repository plus, if present, the local agent config on this
machine — markdown skills, JSON tool schemas and YAML frontmatter, which is what
contextlint actually counts. Calibrating on prose would flatter the result.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contextlint.tokens import heuristic_count  # noqa: E402

SUFFIXES = (".md", ".json", ".mdc", ".toml", ".yaml", ".yml", ".txt")
SKIP = {".git", "node_modules", ".venv", "__pycache__", "dist", "build", ".pytest_cache"}
MIN_CHARS = 120
MAX_FILES = 1500


def corpus(roots: list[Path]) -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if len(docs) >= MAX_FILES:
                break
            if not p.is_file() or p.suffix not in SUFFIXES:
                continue
            if any(part in SKIP for part in p.parts):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(text) >= MIN_CHARS:
                docs.append((str(p), text))
    return docs


def main(argv: list[str]) -> int:
    try:
        import tiktoken
    except ImportError:
        print("tiktoken is required. Run:\n  uv run --with tiktoken benchmarks/calibrate.py")
        return 2

    repo = Path(__file__).resolve().parents[1]
    roots = [Path(a).expanduser() for a in argv[1:]] or [
        repo,
        Path.home() / ".claude" / "skills",
        Path.home() / ".claude" / "plugins",
    ]
    docs = corpus(roots)
    if not docs:
        print("empty corpus")
        return 1

    enc = tiktoken.get_encoding("o200k_base")
    rows, errs = [], []
    total_true = total_est = 0
    by_ext: dict[str, list[float]] = {}

    for path, text in docs:
        true = len(enc.encode(text, disallowed_special=()))
        est = heuristic_count(text)
        if true == 0:
            continue
        err = (est - true) / true
        rows.append({"path": path, "true": true, "est": est, "err": round(err, 4)})
        errs.append(err)
        total_true += true
        total_est += est
        by_ext.setdefault(Path(path).suffix, []).append(err)

    abs_errs = sorted(abs(e) for e in errs)
    result = {
        "files": len(rows),
        "corpus_roots": [str(r) for r in roots],
        "true_tokens": total_true,
        "estimated_tokens": total_est,
        "aggregate_error_pct": round((total_est - total_true) / total_true * 100, 2),
        "median_abs_error_pct": round(statistics.median(abs_errs) * 100, 2),
        "p90_abs_error_pct": round(abs_errs[int(len(abs_errs) * 0.90)] * 100, 2),
        "worst_abs_error_pct": round(abs_errs[-1] * 100, 2),
        "mean_signed_error_pct": round(statistics.fmean(errs) * 100, 2),
        "by_extension": {
            ext: {
                "files": len(v),
                "median_abs_error_pct": round(statistics.median([abs(x) for x in v]) * 100, 2),
            }
            for ext, v in sorted(by_ext.items())
        },
    }

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "calibration.json").write_text(
        json.dumps({"summary": result, "files": rows}, indent=2), encoding="utf-8"
    )

    print("heuristic vs tiktoken/o200k_base")
    print(f"  corpus                {result['files']:,} files, {total_true:,} true tokens")
    print(f"  aggregate error       {result['aggregate_error_pct']:+.2f}%   <- the number that matters for a total")
    print(f"  median per-file error {result['median_abs_error_pct']:.2f}%")
    print(f"  p90 per-file error    {result['p90_abs_error_pct']:.2f}%")
    print(f"  worst per-file error  {result['worst_abs_error_pct']:.2f}%")
    for ext, v in result["by_extension"].items():
        print(f"    {ext:<7} {v['files']:>5} files   median {v['median_abs_error_pct']:.2f}%")
    print(f"\n  written to {out_dir / 'calibration.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
