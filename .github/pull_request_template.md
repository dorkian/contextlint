## Summary of Changes

<!-- Provide a concise description of what this PR does and why. -->

## Checklist

- [ ] Unit tests pass: `python -m pytest tests -q`
- [ ] Benchmarks pass: `python benchmarks/run.py`
- [ ] If adding a check: added a fixture to `benchmarks/fixtures/bloated` and an expectation in `benchmarks/run.py`
- [ ] Adheres to the non-negotiable rules in `AGENTS.md` / `CONTRIBUTING.md`
  - [ ] Certain and candidate savings are never summed
  - [ ] Default path remains offline (no network, telemetry, or API calls)
  - [ ] Asset content never appears in output
- [ ] Verified across light and dark themes (if UI/reporting changes)
