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
