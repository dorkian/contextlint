# contextlint — working on this repository

A CLI that audits what an AI coding assistant loads before the user types: always-on token
cost, dead weight, and MCP configuration security, across Claude Code, Codex, Cursor and
Copilot.

## Layout

| Path | What lives there |
|---|---|
| `src/contextlint/adapters/` | one file per assistant; adding one is a file plus a registry entry |
| `src/contextlint/checks/` | one file per rule family; each emits `Finding`s and nothing else |
| `src/contextlint/models.py` | `Asset`, `Finding`, `Report` — the only shared vocabulary |
| `benchmarks/` | the reproduction path for every number in the README |
| `docs/assets/` | generated charts; never hand-edit an SVG here |

## Commands

```bash
pip install -e ".[dev]"
python -m pytest tests -q                  # 109 tests, fast
python benchmarks/run.py                   # detection + savings, exits 1 if detection regresses
python docs/assets/make_charts.py          # regenerate charts after changing measured data
contextlint audit --no-global .            # dogfood
```

## Rules that are not negotiable

- **Never claim a savings percentage `benchmarks/run.py` cannot reproduce.** The entire
  differentiator over the incumbent tools is that our numbers have a command attached.
- **`audit` never writes.** Anything that touches a user's files goes behind `fix --apply`,
  refuses a dirty git tree, and leaves a restorable backup.
- **Certain and candidate savings are never summed.** They answer different questions.
- **The default path stays offline.** No network, no API key, no telemetry. `--mcp-probe` and
  `--tokenizer anthropic` are the two opt-in exceptions and both announce themselves.
- **Asset content never reaches the output.** JSON and HTML carry names, paths and counts.
- Security findings are heuristics over configuration. Report the matched pattern and let the
  reader judge; never phrase one as proof of a vulnerability.

## When adding a check

Put it in its own file, append it to `CHECKS`, and add a defect instance to
`benchmarks/fixtures/bloated` plus an expectation in `benchmarks/run.py`. A check with no
fixture case is not covered by the detection number, which makes that number a lie by omission.

## When touching the tokenizer

Re-run `benchmarks/tune.py` and `benchmarks/calibrate.py`, and update the README's error
figures. The shipped parameters are fitted on half the corpus so the published error stays
out-of-sample — keep it that way.
