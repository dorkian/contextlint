"""Drift and health. A repeated audit is only a health check if it can compare."""

from pathlib import Path

import pytest

from contextlint.history import (
    FAIL, OK, WARN, Drift, Snapshot, append, assess, fingerprint, latest, load,
)


def _snap(**kw) -> Snapshot:
    base = dict(at="2026-01-01T00:00:00+00:00", always_on=8_000, on_demand=100,
                assets=50, certain=100, candidate=900, findings=3,
                severity={"critical": 0, "high": 0, "medium": 3, "low": 0, "info": 0},
                window=200_000, prints=["budget|a", "hygiene|b", "usage|c"])
    base.update(kw)
    return Snapshot(**base)


def test_fingerprint_ignores_the_numbers_inside_a_title():
    """Titles quote live counts; without this every run looks entirely new."""
    a = fingerprint("mcp-cost", "MCP server 'github' publishes 26 tools costing 3,517 tokens")
    b = fingerprint("mcp-cost", "MCP server 'github' publishes 27 tools costing 3,690 tokens")
    assert a == b


def test_fingerprint_still_separates_different_findings():
    assert fingerprint("hygiene", "skill 'a' is empty") != fingerprint("hygiene", "skill 'b' is empty")
    assert fingerprint("hygiene", "x") != fingerprint("security", "x")


def test_first_run_reports_no_drift():
    d = Drift(None, _snap())
    assert d.first_run and d.token_delta == 0 and not d.new_findings


def test_drift_detects_new_and_resolved():
    prev = _snap(prints=["budget|a", "hygiene|b"])
    cur = _snap(always_on=10_000, prints=["budget|a", "security|new"])
    d = Drift(prev, cur)
    assert d.token_delta == 2_000
    assert d.new_findings == ["security|new"]
    assert d.resolved_findings == ["hygiene|b"]


@pytest.mark.parametrize("field,value", [("probed", True), ("tokenizer", "tiktoken")])
def test_a_different_measurement_mode_is_not_comparable(field, value):
    """A probed run against an unprobed one would report a phantom swing."""
    prev = _snap()
    cur = _snap(**{field: value})
    assert not Drift(prev, cur).comparable()


def test_healthy_setup_passes():
    h = assess(Drift(_snap(), _snap()), warn_ratio=0.05, fail_ratio=0.15)
    assert h.status == OK and h.exit_code == 0 and not h.reasons


def test_budget_thresholds():
    warn = assess(Drift(None, _snap(always_on=11_000)), warn_ratio=0.05, fail_ratio=0.15)
    assert warn.status == WARN and warn.exit_code == 0

    fail = assess(Drift(None, _snap(always_on=40_000)), warn_ratio=0.05, fail_ratio=0.15)
    assert fail.status == FAIL and fail.exit_code == 1


def test_any_open_critical_finding_fails():
    snap = _snap(severity={"critical": 1, "high": 0, "medium": 0, "low": 0, "info": 0})
    h = assess(Drift(None, snap), warn_ratio=0.5, fail_ratio=0.9)
    assert h.status == FAIL and "critical" in h.reasons[0]


def test_a_new_high_finding_fails():
    prev = _snap(severity={"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0})
    cur = _snap(severity={"critical": 0, "high": 2, "medium": 0, "low": 0, "info": 0},
                prints=["security|new one"])
    h = assess(Drift(prev, cur), warn_ratio=0.5, fail_ratio=0.9)
    assert h.status == FAIL


def test_growth_limit():
    prev, cur = _snap(always_on=8_000), _snap(always_on=11_000)
    ok = assess(Drift(prev, cur), warn_ratio=0.5, fail_ratio=0.9, growth_limit=5_000)
    assert ok.status == OK
    bad = assess(Drift(prev, cur), warn_ratio=0.5, fail_ratio=0.9, growth_limit=1_000)
    assert bad.status == FAIL and "grew by" in bad.reasons[0]


def test_history_round_trip(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    assert load(p) == [] and latest(p) is None
    append(p, _snap(always_on=1))
    append(p, _snap(always_on=2))
    assert [s.always_on for s in load(p)] == [1, 2]
    assert latest(p).always_on == 2


def test_a_corrupt_line_does_not_break_the_next_check(tmp_path: Path):
    p = tmp_path / "h.jsonl"
    append(p, _snap(always_on=7))
    p.write_text(p.read_text() + "{not json\n")
    assert [s.always_on for s in load(p)] == [7]
