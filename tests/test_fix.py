import shutil
import subprocess
from pathlib import Path

import pytest

from contextlint.audit import run_audit
from contextlint.fix import _safe_name, apply_plan, build_plan, git_is_clean, render_plan, restore


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

    assert (backup / "manifest.json").exists()
    assert (backup / "restore.sh").exists()

    # Restore through the manifest, not the shell script: the undo has to work on
    # Windows too, where `sh` may not exist at all.
    restored, skipped = restore(backup)
    assert restored and not skipped
    assert all(p.exists() for p in targets), "restore must put every file back"


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


def test_backup_name_is_portable():
    """A Windows absolute path must not survive into the backup filename.

    Leaving `C:\\Users\\...` intact makes the backup destination resolve to the
    source path itself, so `fix --apply` silently backs a file up over itself and
    then declines to delete anything.
    """
    from pathlib import PureWindowsPath

    name = _safe_name(Path("/home/u/ws/.claude/skills/alpha"))
    assert "/" not in name and name.startswith("home__u")

    # simulate the Windows shape without needing to run on Windows
    winish = _safe_name(Path(*PureWindowsPath(r"C:\Users\u\ws\alpha").parts))
    for illegal in (":", "\\", "/", "?", "*", '"'):
        assert illegal not in winish


def test_restore_refuses_to_clobber(tmp_path, fixture_path):
    ws = _workspace(tmp_path, fixture_path)
    plan = build_plan(run_audit(str(ws), include_global=False, use_usage=False))
    targets = [p for p, _ in plan.deletions]
    _, backup = apply_plan(plan, ws)

    # someone re-creates one of the removed paths by hand before restoring
    targets[0].parent.mkdir(parents=True, exist_ok=True)
    targets[0].write_text("hand-written replacement")

    restored, skipped = restore(backup)
    assert skipped, "an occupied path must be left alone, not silently overwritten"
    assert targets[0].read_text() == "hand-written replacement"

    restored_forced, _ = restore(backup, force=True)
    assert restored_forced >= 1


def test_restore_without_a_manifest_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        restore(tmp_path)
