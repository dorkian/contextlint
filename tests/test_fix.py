import shutil
import subprocess

from contextlint.audit import run_audit
from contextlint.fix import apply_plan, build_plan, git_is_clean, render_plan


def _workspace(tmp_path, fixture_path):
    dest = tmp_path / "ws"
    shutil.copytree(fixture_path, dest)
    return dest


def test_plan_only_targets_provably_safe_deletions(tmp_path, fixture_path):
    ws = _workspace(tmp_path, fixture_path)
    report = run_audit(str(ws), include_global=False, use_usage=False)
    plan = build_plan(report)
    assert plan.deletions, "the fixture contains a byte-identical duplicate"
    for _, finding in plan.deletions:
        assert finding.confidence == "certain" or finding.fixable
        assert finding.check in ("duplication", "hygiene")


def test_render_plan_names_every_file(tmp_path, fixture_path):
    ws = _workspace(tmp_path, fixture_path)
    plan = build_plan(run_audit(str(ws), include_global=False, use_usage=False))
    text = render_plan(plan)
    for p, _ in plan.deletions:
        assert str(p) in text


def test_apply_is_reversible(tmp_path, fixture_path):
    ws = _workspace(tmp_path, fixture_path)
    plan = build_plan(run_audit(str(ws), include_global=False, use_usage=False))
    targets = [p for p, _ in plan.deletions]
    assert all(p.exists() for p in targets)

    removed, backup = apply_plan(plan, ws)
    assert removed == len(targets)
    assert not any(p.exists() for p in targets)

    restore = backup / "restore.sh"
    assert restore.exists() and restore.stat().st_mode & 0o111

    subprocess.run(["sh", str(restore)], check=True, capture_output=True)
    assert all(p.exists() for p in targets), "restore.sh must put every file back"


def test_git_guard_reports_dirty_tree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True, env=env)
    assert git_is_clean(repo)[0] is True

    (repo / "a.txt").write_text("changed")
    clean, why = git_is_clean(repo)
    assert clean is False and "uncommitted" in why


def test_non_git_directory_is_not_clean(tmp_path):
    clean, why = git_is_clean(tmp_path)
    assert clean is False and "not a git repository" in why


def test_plan_skips_paths_that_vanished(tmp_path, fixture_path):
    ws = _workspace(tmp_path, fixture_path)
    report = run_audit(str(ws), include_global=False, use_usage=False)
    for f in report.findings:
        for raw in (f.fix_hint or {}).get("paths", []):
            from pathlib import Path

            p = Path(raw)
            if p.exists():
                p.unlink()
    plan = build_plan(report)
    assert not plan.deletions
    assert plan.skipped
