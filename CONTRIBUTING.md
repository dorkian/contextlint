# Contributing to contextlint

Thank you for contributing to `contextlint`! This project audits what AI coding assistants silently load before the user types, measuring always-on context cost, configuration hygiene, and MCP security exposure.

## Architecture

| Path | Purpose |
|---|---|
| `src/contextlint/adapters/` | One file per assistant (`claude_code.py`, `codex.py`, `cursor.py`, `copilot.py`). |
| `src/contextlint/checks/` | One file per check rule family (`budget.py`, `duplication.py`, `hygiene.py`, `usage.py`, `security.py`). Each check consumes `list[Asset]` and emits `Finding`s. |
| `src/contextlint/models.py` | `Asset`, `Finding`, `Report` — the core shared vocabulary. |
| `benchmarks/` | The reproduction harness for published claims in the README. |
| `dashboard/` | Interactive localhost React/Vite dashboard. |

## Development setup

```bash
git clone https://github.com/dorkian/contextlint.git
cd contextlint
pip install -e ".[dev]"
```

Run the tests (fast, no external dependencies):

```bash
python -m pytest tests -q
```

Run the benchmark detection & savings suite:

```bash
python benchmarks/run.py
```

## Non-negotiable rules

1. **Never claim a savings percentage `benchmarks/run.py` cannot reproduce.**
   Our differentiation is that every published number has a reproduction command attached.
2. **`audit` never writes.** Anything that touches a user's files goes behind `fix --apply`, refuses a dirty git working tree, and leaves a restorable backup.
3. **Certain and candidate savings are never summed.**
   Certain savings (byte-identical duplicates, empty assets) have zero behavioral risk. Candidate savings (unused skills, oversized rules) require human judgment.
4. **Offline by default.** No network, no API key, no telemetry. `--mcp-probe` and `--tokenizer anthropic` are the only opt-in exceptions, and both announce themselves.
5. **Asset content never reaches output.** JSON, HTML, and terminal outputs carry identifiers, names, paths, and token counts — never raw asset text or prompt content.

## Adding an assistant adapter

1. Create `src/contextlint/adapters/<assistant_name>.py` implementing `detect(self, ws: Workspace) -> bool` and `collect(self, ws: Workspace) -> list[Asset]`.
2. Register the adapter in `src/contextlint/adapters/__init__.py`.
3. Add tests in `tests/test_adapters.py` verifying detection and loading mode assignment (`ALWAYS`, `ON_DEMAND`, `CONDITIONAL`).

## Adding a check

1. Create or extend a file in `src/contextlint/checks/`.
2. Ensure each check emits `Finding` objects with `severity`, `confidence` (`CERTAIN` or `CANDIDATE`), title, detail, and remediation suggestion.
3. Add a defect instance to `benchmarks/fixtures/bloated/` and an expectation in `benchmarks/run.py`. A check with no benchmark fixture is not covered by our detection statistics.

## Submitting anonymized test fixtures

We welcome real-world, anonymized configurations from Claude Code, Cursor, Codex, and Copilot users to improve our test suite and reduce false positives. See our [Fixture Submission Template](.github/ISSUE_TEMPLATE/fixture_submission.md).
