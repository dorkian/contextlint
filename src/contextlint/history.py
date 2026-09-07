"""Snapshots and drift, so a repeated audit becomes a health check.

Running the same audit on a timer tells you almost nothing on its own. What you
want to know is whether the number moved, and which findings are *new* since the
last time you looked. So each run appends a small snapshot to a JSONL history and
is compared against the previous one.

Snapshots hold aggregates and finding fingerprints only — never asset content, and
never file paths beyond what a finding already carries in its own title.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CRITICAL, HIGH, Report

DEFAULT_HISTORY = ".contextlint-history.jsonl"
MAX_HISTORY = 500

# Findings quote live numbers in their titles ("costs 3,517 tokens"). Fingerprints
# must survive those wobbling, or every run looks like it resolved and re-raised
# everything.
_NUMBERS = re.compile(r"\d[\d,._]*")


def fingerprint(check: str, title: str) -> str:
    return f"{check}|{_NUMBERS.sub('#', title).strip()}"


@dataclass
class Snapshot:
    at: str
    always_on: int
    on_demand: int
    assets: int
    certain: int
    candidate: int
    findings: int
    severity: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)
    assistants: list[str] = field(default_factory=list)
    tokenizer: str = "heuristic"
    probed: bool = False
    window: int = 200_000
    prints: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, report: Report) -> "Snapshot":
        m = report.meta
        return cls(
            at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            always_on=report.always_on_tokens,
            on_demand=report.on_demand_tokens,
            assets=len(report.assets),
            certain=report.certain_tokens,
            candidate=report.candidate_tokens,
            findings=len(report.findings),
            severity=report.counts_by_severity(),
            by_kind=report.by_kind(),
            assistants=list(m.get("assistants_detected") or []),
            tokenizer=str(m.get("tokenizer", "heuristic")),
            probed=bool(m.get("mcp_probed")),
            window=int((m.get("policy") or {}).get("context_window", 200_000)),
            prints=sorted({fingerprint(f.check, f.title) for f in report.findings}),
        )

    @property
    def ratio(self) -> float:
        return self.always_on / self.window if self.window else 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Snapshot":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Drift:
    previous: Snapshot | None
    current: Snapshot

    @property
    def first_run(self) -> bool:
        return self.previous is None

    @property
    def token_delta(self) -> int:
        return 0 if self.previous is None else self.current.always_on - self.previous.always_on

    @property
    def asset_delta(self) -> int:
        return 0 if self.previous is None else self.current.assets - self.previous.assets

    @property
    def new_findings(self) -> list[str]:
        if self.previous is None:
            return []
        return sorted(set(self.current.prints) - set(self.previous.prints))

    @property
    def resolved_findings(self) -> list[str]:
        if self.previous is None:
            return []
        return sorted(set(self.previous.prints) - set(self.current.prints))

    def severity_delta(self, level: str) -> int:
        if self.previous is None:
            return 0
        return self.current.severity.get(level, 0) - self.previous.severity.get(level, 0)

    def comparable(self) -> bool:
        """A probed run and an unprobed one are not the same measurement.

        Comparing them reports a phantom multi-thousand-token swing, so drift is
        suppressed rather than reported as a change that did not happen.
        """
        p = self.previous
        return p is not None and p.probed == self.current.probed and p.tokenizer == self.current.tokenizer


# --- health verdict ----------------------------------------------------------

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Health:
    status: str
    reasons: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {OK: 0, WARN: 0, FAIL: 1}[self.status]


def assess(drift: Drift, *, warn_ratio: float, fail_ratio: float,
           growth_limit: int | None = None) -> Health:
    cur = drift.current
    reasons: list[str] = []
    status = OK

    if cur.ratio >= fail_ratio:
        status = FAIL
        reasons.append(f"always-on is {cur.ratio:.1%} of the window (limit {fail_ratio:.0%})")
    elif cur.ratio >= warn_ratio:
        status = WARN
        reasons.append(f"always-on is {cur.ratio:.1%} of the window (warn at {warn_ratio:.0%})")

    if cur.severity.get(CRITICAL):
        status = FAIL
        reasons.append(f"{cur.severity[CRITICAL]} critical finding(s) open")

    if drift.comparable():
        new_serious = [p for p in drift.new_findings if p.startswith("security|")]
        if drift.severity_delta(HIGH) > 0:
            status = FAIL if status != FAIL else status
            reasons.append(f"{drift.severity_delta(HIGH)} new high-severity finding(s) since last run")
        elif new_serious:
            status = WARN if status == OK else status
            reasons.append(f"{len(new_serious)} new security finding(s) since last run")

        if growth_limit is not None and drift.token_delta > growth_limit:
            status = FAIL
            reasons.append(
                f"always-on grew by {drift.token_delta:,} tokens since last run "
                f"(limit {growth_limit:,})"
            )
    return Health(status, reasons)


# --- storage -----------------------------------------------------------------

def load(path: Path) -> list[Snapshot]:
    if not path.is_file():
        return []
    out: list[Snapshot] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Snapshot.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue  # a corrupt line must not break the next health check
    return out


def append(path: Path, snap: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load(path)
    existing.append(snap)
    trimmed = existing[-MAX_HISTORY:]
    path.write_text(
        "\n".join(json.dumps(s.to_dict()) for s in trimmed) + "\n", encoding="utf-8"
    )


def latest(path: Path) -> Snapshot | None:
    hist = load(path)
    return hist[-1] if hist else None
