import json

import pytest

from contextlint.cli import main


def test_bare_invocation_defaults_to_audit(fixture_path, capsys):
    assert main([str(fixture_path), "--no-global", "--no-usage"]) == 0
    assert "ALWAYS-ON CONTEXT" in capsys.readouterr().out


def test_json_output_is_valid(fixture_path, capsys):
    main([str(fixture_path), "--no-global", "--no-usage", "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["totals"]["asset_count"] > 0
    assert data["meta"]["assistants_detected"]


@pytest.mark.parametrize("level,expected", [("critical", 1), ("never", 0)])
def test_fail_on_exit_codes(fixture_path, level, expected, capsys):
    code = main([str(fixture_path), "--no-global", "--no-usage", "--fail-on", level])
    capsys.readouterr()
    assert code == expected


def test_fail_on_is_clean_when_nothing_is_wrong(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("# Project\nBuild with make.\n")
    code = main([str(tmp_path), "--no-global", "--no-usage", "--fail-on", "medium"])
    capsys.readouterr()
    assert code == 0


def test_html_report_is_self_contained(fixture_path, tmp_path, capsys):
    out = tmp_path / "r.html"
    main([str(fixture_path), "--no-global", "--no-usage", "--html", str(out)])
    capsys.readouterr()
    html = out.read_text()
    assert html.startswith("<!doctype html>")
    assert "<svg" in html
    assert "http://" not in html.split("<style>")[0], "no external resources in the head"
    for marker in ("cdn.", "googleapis", "unpkg", "jsdelivr"):
        assert marker not in html


def test_checks_subcommand_lists_everything(capsys):
    assert main(["checks"]) == 0
    out = capsys.readouterr().out
    for name in ("claude_code", "cursor", "copilot", "codex", "security", "usage"):
        assert name in out


def test_fix_without_apply_changes_nothing(fixture_path, capsys):
    before = sorted(p.name for p in fixture_path.rglob("SKILL.md"))
    assert main(["fix", str(fixture_path), "--no-global", "--no-usage"]) == 0
    assert "Re-run with --apply" in capsys.readouterr().out
    assert sorted(p.name for p in fixture_path.rglob("SKILL.md")) == before


def test_fix_refuses_on_a_non_git_tree(tmp_path, fixture_path, capsys):
    import shutil

    ws = tmp_path / "ws"
    shutil.copytree(fixture_path, ws)
    code = main(["fix", str(ws), "--no-global", "--no-usage", "--apply", "--yes"])
    assert code == 2
    assert "Refusing to write" in capsys.readouterr().err


def test_assistant_filter(fixture_path, capsys):
    main([str(fixture_path), "--no-global", "--no-usage", "--assistant", "cursor",
          "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data["meta"]["assistants_detected"] == ["cursor"]


# --- watch ------------------------------------------------------------------

@pytest.mark.parametrize("value,seconds", [
    ("30s", 30), ("15m", 900), ("6h", 21600), ("1d", 86400), ("90", 90), ("1.5h", 5400),
])
def test_interval_parsing(value, seconds):
    from contextlint.cli import duration

    assert duration(value) == seconds


@pytest.mark.parametrize("value", ["", "abc", "5x", "1", "-3m", "0"])
def test_invalid_intervals_are_rejected(value):
    import argparse

    from contextlint.cli import duration

    with pytest.raises(argparse.ArgumentTypeError):
        duration(value)


@pytest.mark.parametrize("value,fraction", [("5%", 0.05), ("5", 0.05), ("0.05", 0.05), ("100%", 1.0)])
def test_percent_parsing(value, fraction):
    from contextlint.cli import percent

    assert percent(value) == pytest.approx(fraction)


def test_watch_once_writes_history_and_reports_drift(fixture_path, tmp_path, capsys):
    h = tmp_path / "h.jsonl"
    args = [str(fixture_path), "--no-global", "--no-usage", "--once", "--history", str(h)]

    main(["watch", *args])
    first = capsys.readouterr().out
    assert "first run" in first
    assert h.exists()

    main(["watch", *args])
    second = capsys.readouterr().out
    assert "no change" in second
    assert len(h.read_text().strip().splitlines()) == 2


def test_watch_json_is_one_object_per_check(fixture_path, tmp_path, capsys):
    h = tmp_path / "h.jsonl"
    main(["watch", str(fixture_path), "--no-global", "--no-usage", "--once",
          "--history", str(h), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] in ("ok", "warn", "fail")
    assert "snapshot" in payload and "drift" in payload


def test_watch_exit_code_reflects_health(fixture_path, tmp_path, capsys):
    """The fixture carries critical findings, so a health check over it must fail."""
    h = tmp_path / "h.jsonl"
    code = main(["watch", str(fixture_path), "--no-global", "--no-usage", "--once",
                 "--history", str(h)])
    capsys.readouterr()
    assert code == 1


def test_watch_is_clean_on_a_healthy_project(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("# Project\nBuild with make.\n")
    code = main(["watch", str(tmp_path), "--no-global", "--no-usage", "--once",
                 "--history", str(tmp_path / "h.jsonl")])
    capsys.readouterr()
    assert code == 0


def test_watch_quiet_says_nothing_when_healthy(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("# Project\nBuild with make.\n")
    main(["watch", str(tmp_path), "--no-global", "--no-usage", "--once", "--quiet",
          "--history", str(tmp_path / "h.jsonl")])
    assert capsys.readouterr().out.strip() == ""


def test_watch_max_growth_fails_the_check(tmp_path, fixture_path, capsys):
    import shutil

    ws = tmp_path / "ws"
    shutil.copytree(fixture_path, ws)
    h = tmp_path / "h.jsonl"
    common = ["watch", str(ws), "--no-global", "--no-usage", "--once", "--history", str(h),
              "--warn-at", "90%", "--fail-at", "95%", "--max-growth", "5"]

    main(common)
    capsys.readouterr()

    big = ws / ".claude" / "skills" / "grower"
    big.mkdir(parents=True)
    big.joinpath("SKILL.md").write_text(
        "---\nname: grower\ndescription: " + "a much longer description. " * 20 + "\n---\nbody\n"
    )
    code = main(common)
    out = capsys.readouterr().out
    assert code == 1
    assert "grew by" in out


# --- restore ----------------------------------------------------------------

def test_restore_command_round_trip(tmp_path, fixture_path, capsys):
    import shutil

    ws = tmp_path / "ws"
    shutil.copytree(fixture_path, ws)
    dupes = list(ws.rglob("alpha/SKILL.md"))
    assert len(dupes) >= 2

    main(["fix", str(ws), "--no-global", "--no-usage", "--apply", "--allow-dirty", "--yes"])
    out = capsys.readouterr().out
    assert "contextlint restore" in out

    backup = next((ws / ".contextlint-backups").iterdir())
    assert main(["restore", str(backup)]) == 0
    assert "Restored" in capsys.readouterr().out


def test_restore_on_a_missing_backup_errors(tmp_path, capsys):
    code = main(["restore", str(tmp_path / "nope")])
    capsys.readouterr()
    assert code == 2


# --- packaging --------------------------------------------------------------

def test_version_is_declared_once_and_agrees():
    """pyproject and __init__ must not drift; the release workflow checks the tag
    against pyproject, so a mismatch here would ship a package whose --version lies."""
    import re
    import tomllib
    from pathlib import Path

    import contextlint

    root = Path(__file__).resolve().parents[1]
    packaged = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert contextlint.__version__ == packaged


def test_console_script_is_wired_to_main():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["contextlint"] == "contextlint.cli:main"
