"""The only code in this project that writes to your files.

Three guarantees, in order of how much they matter:

1. Nothing happens without ``--apply``. ``contextlint fix`` prints a plan and exits.
2. It refuses to run on a dirty git tree, so ``git checkout .`` is always a valid undo.
3. Every removed file is copied into a timestamped backup with a generated
   ``restore.sh``, so the undo works even outside git.

The failure mode being designed against is documented in the field: an optimizer
that silently rewrites config and leaves the user unable to tell what changed or
why their agent stopped working.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Finding, Report

BACKUP_DIR = ".contextlint-backups"


@dataclass
class FixPlan:
    deletions: list[tuple[Path, Finding]]
    skipped: list[tuple[Finding, str]]

    @property
    def tokens_reclaimed(self) -> int:
        seen: dict[str, int] = {}
        for _, f in self.deletions:
            seen[f.asset_id or f.title] = f.tokens_at_stake
        return sum(seen.values())

    def __bool__(self) -> bool:
        return bool(self.deletions)


def build_plan(report: Report) -> FixPlan:
    deletions: list[tuple[Path, Finding]] = []
    skipped: list[tuple[Finding, str]] = []
    seen: set[Path] = set()

    for f in report.sorted_findings():
        if not f.fixable:
            continue
        hint = f.fix_hint or {}
        if hint.get("action") != "delete":
            skipped.append((f, f"unsupported action {hint.get('action')!r}"))
            continue
        for raw in hint.get("paths") or []:
            p = Path(raw)
            if p in seen:
                continue
            if not p.exists():
                skipped.append((f, f"{p} no longer exists"))
                continue
            seen.add(p)
            deletions.append((p, f))
    return FixPlan(deletions, skipped)


def render_plan(plan: FixPlan) -> str:
    if not plan:
        return "Nothing is safely auto-fixable. Every remaining finding needs a judgement call."
    lines = ["Planned changes:", ""]
    for p, f in plan.deletions:
        parent = p.parent if p.name in ("SKILL.md", "AGENTS.md", "CLAUDE.md") else None
        target = f"{p}  (and its directory {parent})" if parent and _only_child(p) else str(p)
        lines.append(f"  delete  {target}")
        lines.append(f"          {f.title}")
    lines += [
        "",
        f"Reclaims about {plan.tokens_reclaimed:,} always-on tokens.",
    ]
    if plan.skipped:
        lines += ["", "Skipped:"]
        lines += [f"  {f.title} — {why}" for f, why in plan.skipped]
    return "\n".join(lines)


def git_is_clean(root: Path) -> tuple[bool, str]:
    if not (root / ".git").exists():
        return False, "not a git repository"
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git unavailable: {exc}"
    if out.returncode != 0:
        return False, out.stderr.strip() or "git status failed"
    return (not out.stdout.strip()), "working tree has uncommitted changes" if out.stdout.strip() else ""


def apply_plan(plan: FixPlan, root: Path) -> tuple[int, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = root / BACKUP_DIR / stamp
    backup.mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    removed = 0

    for p, _ in plan.deletions:
        target = p.parent if (p.name == "SKILL.md" and _only_child(p)) else p
        dest = backup / _safe_name(target)
        try:
            if target.is_dir():
                shutil.copytree(target, dest)
                shutil.rmtree(target)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
                target.unlink()
        except OSError as exc:
            print(f"contextlint: could not remove {target}: {exc}")
            continue
        removed += 1
        restored.append(f'cp -R "{dest.name}" "{target}"')

    script = backup / "restore.sh"
    script.write_text(
        "#!/bin/sh\n"
        "# Undo the contextlint fix run of " + stamp + ".\n"
        'cd "$(dirname "$0")" || exit 1\n'
        + "\n".join(restored)
        + "\necho 'contextlint: restored.'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return removed, backup


def _only_child(p: Path) -> bool:
    try:
        return sum(1 for _ in p.parent.iterdir()) == 1
    except OSError:
        return False


def _safe_name(p: Path) -> str:
    return str(p).lstrip("/").replace("/", "__")
