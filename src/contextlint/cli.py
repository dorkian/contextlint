"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .adapters import ADAPTERS
from .audit import run_audit
from .checks import CHECKS, Policy
from .models import CRITICAL, HIGH
from .report import render_terminal, write_html
from . import history as hist

EPILOG = """\
examples:
  contextlint audit                      audit the current project plus your global config
  contextlint audit --html report.html   write the visual report
  contextlint audit --mcp-probe          measure real MCP tool-schema cost (starts servers)
  contextlint audit --format json        machine-readable output
  contextlint audit --fail-on high       non-zero exit for CI
  contextlint fix --apply                remove safely-removable duplicates, with a backup
  contextlint watch --every 6h           keep checking, and report what changed
  contextlint watch --once               one check with drift — the form to put in cron
  contextlint restore <backup-dir>       undo a fix run, on any platform
"""

DURATION = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhd]?)$", re.I)
_UNIT = {"s": 1, "": 1, "m": 60, "h": 3600, "d": 86400}


def duration(value: str) -> float:
    """Parse 30s / 15m / 6h / 1d (bare numbers are seconds)."""
    m = DURATION.match(value.strip())
    if not m:
        raise argparse.ArgumentTypeError(
            f"invalid interval {value!r}; use forms like 30s, 15m, 6h, 1d"
        )
    seconds = float(m.group(1)) * _UNIT[m.group(2).lower()]
    if seconds < 5:
        raise argparse.ArgumentTypeError("interval must be at least 5s")
    return seconds


def percent(value: str) -> float:
    """Accept 5, 5%, or 0.05 and return a fraction."""
    v = value.strip().rstrip("%")
    try:
        n = float(v)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid percentage {value!r}") from None
    if value.strip().endswith("%") or n > 1:
        n /= 100
    if not 0 < n <= 1:
        raise argparse.ArgumentTypeError("percentage must be above 0 and at most 100%")
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="contextlint",
        description="Audit what your AI coding assistant loads before you type: "
                    "token cost, dead weight, and MCP security risk.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"contextlint {__version__}")
    sub = p.add_subparsers(dest="command")

    a = sub.add_parser("audit", help="report on context cost, dead weight and security (read-only)")
    _common(a)
    a.add_argument("--format", choices=("text", "json"), default="text")
    a.add_argument("--html", metavar="PATH", help="also write a self-contained HTML report")
    a.add_argument("--fail-on", choices=("critical", "high", "medium", "low", "never"),
                   default="never", help="exit non-zero when a finding at or above this severity exists")
    a.add_argument("--max-findings", type=int, default=40)
    a.add_argument("-v", "--verbose", action="store_true", help="show file paths for each finding")

    f = sub.add_parser("fix", help="apply the safely-reversible subset of findings")
    _common(f)
    f.add_argument("--apply", action="store_true",
                   help="actually make the changes; without it, the plan is printed and nothing is written")
    f.add_argument("--allow-dirty", action="store_true",
                   help="proceed even though the git working tree is not clean")

    w = sub.add_parser(
        "watch",
        help="run the audit on an interval and report what changed since last time",
        description=(
            "Repeats the audit and compares each run against the previous one, so the "
            "output is drift rather than the same numbers again. Use --once under cron, "
            "systemd or a scheduled CI job when you would rather something else own the "
            "scheduling; the comparison still works because the history file persists."
        ),
    )
    _common(w)
    w.add_argument("--every", type=duration, default=None, metavar="INTERVAL",
                   help="how often to re-check: 30s, 15m, 6h, 1d (default: run once and exit)")
    w.add_argument("--once", action="store_true", help="run a single check and exit")
    w.add_argument("--times", type=int, default=0, metavar="N",
                   help="stop after N checks (default: run until interrupted)")
    w.add_argument("--history", metavar="FILE", default=None,
                   help=f"where snapshots are kept (default: <project>/{hist.DEFAULT_HISTORY})")
    w.add_argument("--warn-at", type=percent, default="5%", metavar="PCT",
                   help="warn when always-on cost reaches this share of the window (default 5%%)")
    w.add_argument("--fail-at", type=percent, default="15%", metavar="PCT",
                   help="fail when always-on cost reaches this share of the window (default 15%%)")
    w.add_argument("--max-growth", type=int, default=None, metavar="TOKENS",
                   help="fail if always-on grows by more than this many tokens between checks")
    w.add_argument("--json", action="store_true", dest="json_out",
                   help="emit one JSON object per check, for log shipping")
    w.add_argument("--quiet", action="store_true",
                   help="print only when the status is not ok")

    r = sub.add_parser("restore", help="undo a `fix --apply` run from its backup directory")
    r.add_argument("backup", help="a directory under .contextlint-backups/")
    r.add_argument("--force", action="store_true",
                   help="overwrite paths that exist again")

    sub.add_parser("checks", help="list the checks and adapters that ship with this version")
    return p


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    p.add_argument("--assistant", action="append", dest="assistants", metavar="NAME",
                   choices=[a.name for a in ADAPTERS],
                   help="limit to one assistant; repeatable")
    p.add_argument("--no-global", action="store_true",
                   help="ignore ~/ config and audit only this project")
    p.add_argument("--tokenizer", choices=("heuristic", "tiktoken", "anthropic"), default="heuristic")
    p.add_argument("--context-window", type=int, default=200_000)
    p.add_argument("--no-usage", action="store_true", help="skip reading session transcripts")
    p.add_argument("--session-logs", action="append", metavar="DIR",
                   help="extra transcript directory; repeatable")
    p.add_argument("--mcp-probe", action="store_true",
                   help="measure real tool schemas by starting each MCP server (executes their commands)")
    p.add_argument("--probe-timeout", type=float, default=20.0)
    p.add_argument("--check", action="append", dest="only_checks", metavar="ID",
                   choices=[c.id for c in CHECKS], help="run only this check; repeatable")
    p.add_argument("--skip-check", action="append", dest="skip_checks", metavar="ID",
                   choices=[c.id for c in CHECKS], help="skip this check; repeatable")
    p.add_argument("--yes", action="store_true", help="skip interactive confirmation prompts")


def _audit_from_args(args) -> "object":
    announced: list[str] = []

    def on_probe(name: str, cmd: str) -> None:
        announced.append(f"  {name}: {cmd}")

    if args.mcp_probe and not args.yes and sys.stdin.isatty():
        print(
            "--mcp-probe starts every configured MCP server so their tool schemas can be measured.\n"
            "This runs third-party code and opens network connections.",
            file=sys.stderr,
        )
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted. Run without --mcp-probe for a purely static audit.", file=sys.stderr)
            raise SystemExit(2)

    report = run_audit(
        args.path,
        assistants=args.assistants,
        include_global=not args.no_global,
        tokenizer=args.tokenizer,
        policy=Policy(context_window=args.context_window),
        use_usage=not args.no_usage,
        session_logs=[Path(d).expanduser() for d in (args.session_logs or [])] or None,
        mcp_probe=args.mcp_probe,
        probe_timeout=args.probe_timeout,
        only_checks=args.only_checks,
        skip_checks=args.skip_checks,
        on_probe=on_probe,
    )
    report.meta["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if announced:
        report.meta["probed_commands"] = announced
    return report


def cmd_audit(args) -> int:
    report = _audit_from_args(args)

    if args.format == "json":
        print(report.to_json())
    else:
        print(render_terminal(report, verbose=args.verbose, max_findings=args.max_findings))

    if args.html:
        out = write_html(report, Path(args.html).expanduser())
        print(f"\nHTML report → {out}", file=sys.stderr)

    if args.fail_on != "never":
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        limit = rank[args.fail_on]
        worst = min((rank.get(f.severity, 9) for f in report.findings), default=9)
        if worst <= limit:
            return 1
    return 0


def cmd_fix(args) -> int:
    from .fix import apply_plan, build_plan, git_is_clean, render_plan

    report = _audit_from_args(args)
    plan = build_plan(report)
    print(render_plan(plan))
    if not plan:
        return 0

    if not args.apply:
        print("\nNothing was changed. Re-run with --apply to make these changes.")
        return 0

    root = Path(report.meta["project"])
    clean, why = git_is_clean(root)
    if not clean and not args.allow_dirty:
        print(
            f"\nRefusing to write: {why}.\n"
            "Commit or stash first so `git checkout .` is a working undo, "
            "or pass --allow-dirty to override.",
            file=sys.stderr,
        )
        return 2

    blocking = [f for f in report.findings if f.severity in (CRITICAL, HIGH) and f.check == "security"]
    if blocking and not args.yes:
        print(f"\nNote: {len(blocking)} unresolved critical/high security finding(s) — "
              "fix does not touch those.")

    if not args.yes and sys.stdin.isatty():
        if input("\nApply these changes? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted; nothing was changed.")
            return 0

    removed, backup = apply_plan(plan, root)
    print(f"\nRemoved {removed} item(s). Backup: {backup}")
    print(f"Undo with: contextlint restore {backup}")
    return 0


ICON = {hist.OK: "ok  ", hist.WARN: "warn", hist.FAIL: "FAIL"}


def _health_line(snap, drift, health) -> str:
    parts = [
        snap.at,
        ICON[health.status].upper() if health.status != hist.OK else "OK  ",
        f"always-on {snap.always_on:,} ({snap.ratio:.1%})",
    ]
    if drift.first_run:
        parts.append("first run — nothing to compare yet")
    elif not drift.comparable():
        parts.append("measurement mode changed — drift not comparable")
    else:
        d = drift.token_delta
        parts.append(f"{'+' if d > 0 else ''}{d:,} since last" if d else "no change")
        if drift.new_findings:
            parts.append(f"new {len(drift.new_findings)}")
        if drift.resolved_findings:
            parts.append(f"resolved {len(drift.resolved_findings)}")
    parts.append(f"findings {snap.findings}")
    return "  ·  ".join(parts)


def cmd_watch(args) -> int:
    project = Path(args.path).expanduser().resolve()
    hist_path = Path(args.history).expanduser() if args.history else project / hist.DEFAULT_HISTORY
    interval = None if (args.once or args.every is None) else args.every
    limit = 1 if (args.once or interval is None) else (args.times or 0)

    worst = 0
    checks = 0
    try:
        while True:
            report = _audit_from_args(args)
            snap = hist.Snapshot.of(report)
            previous = hist.latest(hist_path)
            drift = hist.Drift(previous, snap)
            health = hist.assess(
                drift, warn_ratio=args.warn_at, fail_ratio=args.fail_at,
                growth_limit=args.max_growth,
            )
            hist.append(hist_path, snap)
            worst = max(worst, health.exit_code)
            checks += 1

            if args.json_out:
                print(json.dumps({
                    "status": health.status, "reasons": health.reasons,
                    "snapshot": snap.to_dict(),
                    "drift": {
                        "comparable": drift.comparable(),
                        "token_delta": drift.token_delta,
                        "asset_delta": drift.asset_delta,
                        "new": drift.new_findings,
                        "resolved": drift.resolved_findings,
                    },
                }), flush=True)
            elif not (args.quiet and health.status == hist.OK):
                print(_health_line(snap, drift, health), flush=True)
                for reason in health.reasons:
                    print(f"      → {reason}", flush=True)
                for f in drift.new_findings[:5]:
                    print(f"      + {f.split('|', 1)[1]}", flush=True)

            if limit and checks >= limit:
                break
            if interval is None:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\nstopped after {checks} check(s).", file=sys.stderr)
    return worst


def cmd_restore(args) -> int:
    from .fix import restore

    backup = Path(args.backup).expanduser().resolve()
    try:
        restored, skipped = restore(backup, force=args.force)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"contextlint: {exc}", file=sys.stderr)
        return 2
    print(f"Restored {restored} item(s) from {backup}.")
    for line in skipped:
        print(f"  skipped {line}")
    return 0 if restored or not skipped else 1


def cmd_checks(_args) -> int:
    print("adapters:")
    for a in ADAPTERS:
        print(f"  {a.name:<14} {a.label}")
    print("\nchecks:")
    for c in CHECKS:
        print(f"  {c.id:<14} {c.title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    # bare `contextlint` and `contextlint <path>` both mean audit
    commands = ("audit", "fix", "checks", "watch", "restore")
    if not argv or (argv[0] not in commands and not argv[0].startswith("-")):
        argv = ["audit", *argv]
    elif argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version"):
        argv = ["audit", *argv]

    args = parser.parse_args(argv)
    handler = {
        "audit": cmd_audit, "fix": cmd_fix, "checks": cmd_checks,
        "watch": cmd_watch, "restore": cmd_restore,
    }.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
