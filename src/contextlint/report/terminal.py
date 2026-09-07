"""Terminal report. Colour when it is a TTY, plain text when it is a pipe."""

from __future__ import annotations

import os
import shutil
import sys

from ..models import CRITICAL, HIGH, INFO, LOW, MEDIUM, Report

SEV_COLOR = {CRITICAL: "\033[1;97;41m", HIGH: "\033[1;31m", MEDIUM: "\033[1;33m",
             LOW: "\033[36m", INFO: "\033[2m"}
SEV_LABEL = {CRITICAL: "CRIT", HIGH: "HIGH", MEDIUM: "MED ", LOW: "LOW ", INFO: "INFO"}
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"


def _use_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def render_terminal(report: Report, *, verbose: bool = False, max_findings: int = 40) -> str:
    color = _use_color()
    width = min(shutil.get_terminal_size((100, 24)).columns, 100)

    def c(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    m = report.meta
    total = report.always_on_tokens
    window = m["policy"]["context_window"]
    out: list[str] = []

    out.append(c("contextlint", BOLD) + f"  {m['project']}")
    out.append(DIM_LINE(width, color))
    out.append(
        f"assistants  {', '.join(m['assistants_detected']) or 'none detected'}\n"
        f"assets      {len(report.assets):,}"
        f"   tokenizer {m['tokenizer']}{'' if m['tokenizer_exact'] else ' (estimate)'}"
        f"   {m['elapsed_seconds']}s"
    )
    out.append("")

    # --- headline ------------------------------------------------------------
    pct = total / window if window else 0
    bar = _bar(pct, 40, color)
    out.append(c("ALWAYS-ON CONTEXT", BOLD))
    out.append(f"  {bar} {total:>8,} tok  {pct:5.1%} of {window:,}")
    out.append(f"  {DIM if color else ''}on-demand (loaded only when invoked): "
               f"{report.on_demand_tokens:,} tok{RESET if color else ''}")
    certain, candidate = report.certain_tokens, report.candidate_tokens
    if certain:
        out.append(f"  {c('safe to reclaim', BOLD)}  {certain:>7,} tok "
                   f"({certain / total:.0%})  duplicates and empty assets — removing them "
                   f"cannot change behaviour")
    if candidate:
        out.append(f"  {c('worth reviewing', BOLD)}  {candidate:>7,} tok "
                   f"({candidate / total:.0%})  needs your judgement — see the findings below")
    out.append("")

    # --- breakdown -----------------------------------------------------------
    out.append(c("WHERE IT GOES", BOLD))
    for label, data in (("by assistant", report.by_assistant()), ("by kind", report.by_kind())):
        out.append(f"  {DIM if color else ''}{label}{RESET if color else ''}")
        for k, v in list(data.items())[:8]:
            if not v:
                continue
            out.append(f"    {k:<16} {v:>8,}  {_minibar(v / total if total else 0, 24, color)}")
    out.append("")

    # --- usage ---------------------------------------------------------------
    u = m.get("usage") or {}
    if u.get("available"):
        out.append(c("REAL USAGE", BOLD))
        out.append(
            f"  {u['sessions']:,} sessions over {u['span_days']:.0f} days   "
            f"{u['distinct_skills_invoked']} distinct skills invoked"
        )
        top = sorted(u["skills"].items(), key=lambda kv: -kv[1]["count"])[:5]
        if top:
            out.append("  most used: " + ", ".join(f"{n} ({d['count']}x)" for n, d in top))
        out.append("")

    # --- findings ------------------------------------------------------------
    counts = report.counts_by_severity()
    summary = "  ".join(
        c(f"{SEV_LABEL[s].strip()} {counts[s]}", SEV_COLOR[s]) if counts[s] else f"{SEV_LABEL[s].strip()} 0"
        for s in (CRITICAL, HIGH, MEDIUM, LOW, INFO)
    )
    out.append(c("FINDINGS", BOLD) + f"   {summary}")
    out.append("")

    shown = report.sorted_findings()
    for f in shown[:max_findings]:
        tag = c(f" {SEV_LABEL[f.severity]} ", SEV_COLOR[f.severity])
        cost = f"  {DIM if color else ''}-{f.tokens_at_stake:,} tok{RESET if color else ''}" if f.tokens_at_stake else ""
        out.append(f"{tag} {f.title}{cost}")
        for line in _wrap(f.detail, width - 7):
            out.append(f"       {DIM if color else ''}{line}{RESET if color else ''}")
        if f.remediation:
            for line in _wrap("→ " + f.remediation, width - 7):
                out.append(f"       {line}")
        if verbose and f.path:
            out.append(f"       {DIM if color else ''}{f.path}{RESET if color else ''}")
        out.append("")

    if len(shown) > max_findings:
        out.append(f"  {DIM if color else ''}+{len(shown) - max_findings} more — "
                   f"use --format json or --html for the full set{RESET if color else ''}")
        out.append("")

    if not m["tokenizer_exact"]:
        out.append(DIM_LINE(width, color))
        out.append(
            f"{DIM if color else ''}Token counts are estimated by contextlint's offline heuristic. "
            f"Install `contextlint[exact]` and pass --tokenizer tiktoken for measured counts; "
            f"benchmarks/calibrate.py reports the heuristic's error.{RESET if color else ''}"
        )
    if not m["mcp_probed"] and any(a.kind == "mcp_server" for a in report.assets):
        out.append(
            f"{DIM if color else ''}MCP tool-schema cost is unmeasured and excluded from the totals. "
            f"Add --mcp-probe to measure it.{RESET if color else ''}"
        )
    return "\n".join(out)


def DIM_LINE(width: int, color: bool) -> str:  # noqa: N802 — reads as a constant at call sites
    line = "─" * width
    return f"{DIM}{line}{RESET}" if color else line


def _bar(pct: float, width: int, color: bool) -> str:
    filled = min(int(pct * width), width)
    body = "█" * filled + "·" * (width - filled)
    if not color:
        return body
    code = "\033[31m" if pct >= 0.15 else "\033[33m" if pct >= 0.05 else "\033[32m"
    return f"{code}{body}{RESET}"


def _minibar(pct: float, width: int, color: bool) -> str:
    filled = min(int(pct * width), width)
    body = "▉" * filled
    return f"{DIM}{body}{RESET}" if color else body


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    lines: list[str] = []
    for para in (text or "").split("\n"):
        lines += textwrap.wrap(para, width) or [""]
    return lines
