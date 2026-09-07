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

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Finding, Report

BACKUP_DIR = ".contextlint-backups"
MANIFEST = "manifest.json"

# Characters a Windows filename cannot contain. The backup name is derived from an
# absolute source path, which on Windows starts with a drive letter and a colon.
_ILLEGAL = re.compile(r'[<>:"/\\|?*]')


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
    entries: list[dict[str, str]] = []
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
        entries.append({"backup": dest.name, "original": str(target)})
        restored.append(f'cp -R "{dest.name}" "{target}"')

    # Machine-readable manifest drives `contextlint restore`, which works on every
    # platform. The shell script stays for anyone who prefers it.
    (backup / MANIFEST).write_text(
        json.dumps({"created": stamp, "root": str(root), "entries": entries}, indent=2),
        encoding="utf-8",
    )

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
    """Flatten an absolute path into one portable filename.

    The naive version — strip leading "/" and swap "/" for "__" — is a POSIX
    assumption. On Windows it leaves ``C:\\Users\\...`` untouched, and joining that
    onto the backup directory yields the *source path back*, so the backup copy
    silently targets the file it is meant to preserve.
    """
    parts = [part for part in p.parts if part not in ("/", "\\")]
    cleaned = [_ILLEGAL.sub("_", part).strip(". ") for part in parts]
    return "__".join(x for x in cleaned if x) or "asset"


def restore(backup: Path, *, force: bool = False) -> tuple[int, list[str]]:
    """Put back everything a `fix --apply` run removed.

    Reads the manifest rather than the shell script, so this works identically on
    Windows. Refuses to overwrite anything that exists again unless forced — the
    likeliest reason a path is occupied is that you already restored, or rewrote it
    by hand, and clobbering that would make the undo destructive in its own right.
    """
    manifest = backup / MANIFEST
    if not manifest.is_file():
        raise FileNotFoundError(f"no {MANIFEST} in {backup}")
    data = json.loads(manifest.read_text(encoding="utf-8"))

    restored = 0
    skipped: list[str] = []
    for entry in data.get("entries", []):
        src = backup / entry["backup"]
        dst = Path(entry["original"])
        if not src.exists():
            skipped.append(f"{dst} — backup copy missing")
            continue
        if dst.exists() and not force:
            skipped.append(f"{dst} — already exists, left alone (use --force to overwrite)")
            continue
        try:
            if dst.exists():
                shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        except OSError as exc:
            skipped.append(f"{dst} — {exc}")
            continue
        restored += 1
    return restored, skipped
