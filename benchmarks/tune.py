#!/usr/bin/env python3
"""Fit the heuristic's parameters to a real tokenizer.

    uv run --no-project --with tiktoken python benchmarks/tune.py

Coordinate descent over the seven parameters, minimising the mean absolute
per-file relative error against ``tiktoken`` o200k_base. Prints a
``HeuristicParams(...)`` block to paste into ``src/contextlint/tokens.py``, then
re-run ``calibrate.py`` to publish the resulting error.

Deliberately not automatic: a tool whose headline is measurement honesty should
make changing its own measurement an explicit, reviewed act.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contextlint.tokens import HeuristicParams, heuristic_count  # noqa: E402

from calibrate import corpus  # noqa: E402

GRID = {
    "word_free": [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0],
    "word_step": [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 9.0],
    "digit_group": [2.0, 2.5, 3.0, 3.5, 4.0],
    "symbol_group": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0],
    "ws_spaces": [2.0, 4.0, 6.0, 8.0, 12.0, 20.0, 32.0, 64.0],
    "newline": [0.0, 0.1, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0],
    "nonascii": [0.5, 0.75, 1.0, 1.5],
}


def loss(truths: list[int], texts: list[str], p: HeuristicParams) -> float:
    """Mean absolute relative error, plus a penalty on aggregate bias.

    Per-file accuracy alone would happily accept a model that is 5% high on every
    small file and 5% low on every large one; the aggregate term keeps the total
    honest, which is the number the report actually prints.
    """
    errs = []
    tot_true = tot_est = 0
    for t, txt in zip(truths, texts):
        est = heuristic_count(txt, p)
        errs.append(abs(est - t) / t)
        tot_true += t
        tot_est += est
    agg = abs(tot_est - tot_true) / tot_true
    return statistics.fmean(errs) + agg


def main() -> int:
    try:
        import tiktoken
    except ImportError:
        print("tiktoken required: uv run --no-project --with tiktoken python benchmarks/tune.py")
        return 2

    repo = Path(__file__).resolve().parents[1]
    docs = corpus([repo, Path.home() / ".claude" / "skills", Path.home() / ".claude" / "plugins"])
    enc = tiktoken.get_encoding("o200k_base")
    texts = [t for _, t in docs]
    truths = [len(enc.encode(t, disallowed_special=())) for t in texts]
    keep = [i for i, v in enumerate(truths) if v > 0]
    texts = [texts[i] for i in keep]
    truths = [truths[i] for i in keep]
    # Deterministic split. Fitting and reporting on the same files would produce a
    # flattering number that says nothing about a corpus the author has never seen —
    # which is the specific failure this project criticises in its competitors.
    train_t, train_x = truths[0::2], texts[0::2]
    test_t, test_x = truths[1::2], texts[1::2]
    print(f"corpus: {len(texts)} files, {sum(truths):,} true tokens")
    print(f"split:  {len(train_x)} train / {len(test_x)} held out\n")

    best = HeuristicParams()
    best_loss = loss(train_t, train_x, best)
    print(f"start loss {best_loss:.4f}  {best.as_dict()}")

    for sweep in range(4):
        improved = False
        for field, values in GRID.items():
            for v in values:
                cand = HeuristicParams(**{**best.as_dict(), field: v})
                cand_loss = loss(train_t, train_x, cand)
                if cand_loss < best_loss - 1e-6:
                    best, best_loss, improved = cand, cand_loss, True
        print(f"sweep {sweep + 1}: loss {best_loss:.4f}")
        if not improved:
            break

    def report(name: str, t: list[int], x: list[str]) -> None:
        errs = []
        tot_true = tot_est = 0
        for tv, xv in zip(t, x):
            est = heuristic_count(xv, best)
            errs.append(abs(est - tv) / tv)
            tot_true += tv
            tot_est += est
        agg = (tot_est - tot_true) / tot_true * 100
        med = statistics.median(errs) * 100
        print(f"  {name:<10} aggregate {agg:+6.2f}%   median per-file {med:5.2f}%")

    print("\nfitted parameters evaluated:")
    report("train", train_t, train_x)
    report("held out", test_t, test_x)

    print("\nPaste into src/contextlint/tokens.py:\n")
    print("DEFAULT_PARAMS = HeuristicParams(")
    for k, v in best.as_dict().items():
        print(f"    {k}={v},")
    print(")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
