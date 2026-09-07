from pathlib import Path

from contextlint.models import CANDIDATE, CERTAIN, Asset, Finding, Report


def _asset(name, tokens):
    a = Asset(assistant="x", kind="skill", name=name, path=Path(f"/tmp/{name}"))
    a.always_on_tokens = tokens
    return a


def test_savings_are_not_double_counted():
    """Three checks flagging one skill is one skill's worth of savings."""
    a = _asset("dup", 500)
    r = Report(
        assets=[a],
        findings=[
            Finding(check="duplication", severity="high", title="a", detail="",
                    at_stake_assets=[a.id], tokens_at_stake=500, confidence=CERTAIN),
            Finding(check="usage", severity="medium", title="b", detail="",
                    at_stake_assets=[a.id], tokens_at_stake=500),
            Finding(check="hygiene", severity="low", title="c", detail="",
                    asset_id=a.id, tokens_at_stake=500),
        ],
    )
    assert r.recoverable_tokens == 500


def test_certain_and_candidate_are_disjoint():
    a, b = _asset("dup", 400), _asset("unused", 600)
    r = Report(
        assets=[a, b],
        findings=[
            Finding(check="duplication", severity="high", title="dup", detail="",
                    at_stake_assets=[a.id], confidence=CERTAIN),
            # the same asset also appears in a judgement-call finding
            Finding(check="usage", severity="medium", title="unused", detail="",
                    at_stake_assets=[a.id, b.id], confidence=CANDIDATE),
        ],
    )
    assert r.certain_tokens == 400
    assert r.candidate_tokens == 600, "an asset already counted as certain is not counted again"
    assert r.certain_tokens + r.candidate_tokens == r.recoverable_tokens


def test_unknown_asset_ids_are_ignored():
    r = Report(
        assets=[_asset("real", 100)],
        findings=[Finding(check="x", severity="low", title="ghost", detail="",
                          at_stake_assets=["nope:nope:nope"], tokens_at_stake=9999)],
    )
    assert r.recoverable_tokens == 0


def test_json_round_trips():
    import json

    a = _asset("s", 10)
    r = Report(assets=[a], findings=[], meta={"version": "0"})
    d = json.loads(r.to_json())
    assert d["totals"]["always_on_tokens"] == 10
    assert d["assets"][0]["id"] == a.id
    assert "always_on_text" not in d["assets"][0], "asset text must never leak into the report"
