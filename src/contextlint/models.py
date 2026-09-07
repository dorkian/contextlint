"""Core data model.

Every adapter normalises its assistant's wildly different config formats into
:class:`Asset`. Every check consumes ``list[Asset]`` and emits :class:`Finding`.
Nothing else is shared, which is what keeps "add an assistant" a one-file change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

# --- Loading modes -----------------------------------------------------------
# The single most important distinction in this tool, and the one every existing
# auditor gets wrong: an asset's size on disk is not its cost. A 40 KB skill whose
# body only loads when invoked costs you its *description*, every turn, forever —
# not its body. Conflating the two overstates savings by an order of magnitude.

ALWAYS = "always"           # injected into the system prompt on every request
ON_DEMAND = "on_demand"     # only a catalog entry is always-on; body loads when invoked
CONDITIONAL = "conditional"  # loads when a glob / path / manual reference matches
DEFERRED = "deferred"       # behind a tool-search or lazy-load mechanism
UNKNOWN = "unknown"

LOADING_MODES = (ALWAYS, ON_DEMAND, CONDITIONAL, DEFERRED, UNKNOWN)

# --- Severity ----------------------------------------------------------------

CRITICAL, HIGH, MEDIUM, LOW, INFO = "critical", "high", "medium", "low", "info"
SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3, INFO: 4}

# --- Savings confidence ------------------------------------------------------
# A byte-identical duplicate is a fact: deleting it changes nothing but the bill.
# A skill you have not invoked in 90 days is a question. Reporting both under one
# "you could save 94%" number is how every incumbent's headline percentage got so
# large, so contextlint reports them as two numbers and never adds them together.

CERTAIN = "certain"      # removing this cannot change behaviour
CANDIDATE = "candidate"  # worth reviewing; removing it might change behaviour


@dataclass
class Asset:
    """One thing an assistant loads: a skill, a memory file, a rule, an MCP tool."""

    assistant: str
    kind: str                     # skill | memory | rule | instruction | mcp_server | mcp_tool
    name: str
    loading: str = UNKNOWN
    path: Path | None = None
    always_on_text: str = ""      # the part injected on every request
    on_demand_text: str = ""      # the part injected only when the asset is used
    meta: dict[str, Any] = field(default_factory=dict)

    # populated by tokens.price()
    always_on_tokens: int = 0
    on_demand_tokens: int = 0

    @property
    def id(self) -> str:
        # Name *and* path. Name alone collapses the same skill in two roots, which is
        # precisely what the duplication check exists to find. Path alone collapses
        # every MCP server declared in one .mcp.json into a single asset.
        return f"{self.assistant}:{self.kind}:{self.name}" + (f"@{self.path}" if self.path else "")

    @property
    def total_tokens(self) -> int:
        return self.always_on_tokens + self.on_demand_tokens

    @property
    def bytes_on_disk(self) -> int:
        try:
            return self.path.stat().st_size if self.path else 0
        except OSError:
            return 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["path"] = str(self.path) if self.path else None
        d["id"] = self.id
        d.pop("always_on_text", None)
        d.pop("on_demand_text", None)
        d["meta"] = {k: v for k, v in d["meta"].items() if _jsonable(v)}
        return d


@dataclass
class Finding:
    """One thing worth acting on. Findings are signals, never proof."""

    check: str
    severity: str
    title: str
    detail: str
    remediation: str = ""
    asset_id: str | None = None
    path: Path | None = None
    tokens_at_stake: int = 0      # always-on tokens recoverable if acted on
    refs: list[str] = field(default_factory=list)
    at_stake_assets: list[str] = field(default_factory=list)
    confidence: str = CANDIDATE
    fixable: bool = False          # can `contextlint fix` act on this automatically?
    fix_hint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["path"] = str(self.path) if self.path else None
        return d


@dataclass
class Report:
    assets: list[Asset] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    # --- aggregates ---------------------------------------------------------
    @property
    def always_on_tokens(self) -> int:
        return sum(a.always_on_tokens for a in self.assets)

    @property
    def on_demand_tokens(self) -> int:
        return sum(a.on_demand_tokens for a in self.assets)

    def _at_stake(self, confidence: str | None = None) -> set[str]:
        by_id = {a.id for a in self.assets}
        out: set[str] = set()
        for f in self.findings:
            if confidence and f.confidence != confidence:
                continue
            ids = list(f.at_stake_assets) or ([f.asset_id] if f.asset_id else [])
            out.update(i for i in ids if i in by_id)
        return out

    def _price(self, ids: set[str]) -> int:
        by_id = {a.id: a.always_on_tokens for a in self.assets}
        return sum(by_id[i] for i in ids)

    @property
    def certain_tokens(self) -> int:
        """Tokens recoverable with no behavioural risk: duplicates and empty assets."""
        return self._price(self._at_stake(CERTAIN))

    @property
    def candidate_tokens(self) -> int:
        """Tokens sitting behind a judgement call. Never added to certain_tokens."""
        return self._price(self._at_stake(CANDIDATE) - self._at_stake(CERTAIN))

    @property
    def recoverable_tokens(self) -> int:
        """Always-on tokens you would get back if every finding were acted on.

        Computed as the union of the *assets* the findings put at stake, priced once
        each — not the sum of the findings' own numbers. Three checks flagging the
        same duplicated skill is one skill's worth of savings, not three. Summing
        per-finding claims is how a 30% win gets reported as 90%.
        """
        by_id = {a.id: a.always_on_tokens for a in self.assets}
        at_stake: set[str] = set()
        orphan = 0
        for f in self.findings:
            ids = list(f.at_stake_assets) or ([f.asset_id] if f.asset_id else [])
            known = [i for i in ids if i in by_id]
            if known:
                at_stake.update(known)
            elif f.tokens_at_stake > 0 and not ids:
                orphan = max(orphan, f.tokens_at_stake)
        return sum(by_id[i] for i in at_stake) + orphan

    def by_assistant(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.assets:
            out[a.assistant] = out.get(a.assistant, 0) + a.always_on_tokens
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.assets:
            out[a.kind] = out.get(a.kind, 0) + a.always_on_tokens
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def counts_by_severity(self) -> dict[str, int]:
        out = {s: 0 for s in SEVERITY_ORDER}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), -f.tokens_at_stake, f.title),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "meta": self.meta,
            "totals": {
                "always_on_tokens": self.always_on_tokens,
                "on_demand_tokens": self.on_demand_tokens,
                "recoverable_tokens": self.recoverable_tokens,
                "certain_tokens": self.certain_tokens,
                "candidate_tokens": self.candidate_tokens,
                "asset_count": len(self.assets),
                "by_assistant": self.by_assistant(),
                "by_kind": self.by_kind(),
                "by_severity": self.counts_by_severity(),
            },
            "assets": [a.to_dict() for a in self.assets],
            "findings": [f.to_dict() for f in self.sorted_findings()],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


def _jsonable(v: Any) -> bool:
    try:
        json.dumps(v, default=str)
        return True
    except (TypeError, ValueError):
        return False


def dedupe_assets(assets: Iterable[Asset]) -> list[Asset]:
    """Collapse assets that resolve to the same id, keeping the first seen."""
    out: dict[str, Asset] = {}
    for a in assets:
        out.setdefault(a.id, a)
    return list(out.values())
