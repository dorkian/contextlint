"""Check registry and shared policy.

A check is a plain object with an ``id``, a ``title`` and ``run(ctx) -> list[Finding]``.
No base class, no registration decorator, no plugin manifest: adding a rule is
appending one entry to :data:`CHECKS`. The pluggability that matters here is being
able to *drop* a check without touching anything else, which this gives you for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..discovery import Workspace
from ..models import Asset, Finding


@dataclass
class Policy:
    """Every threshold in one place, so a tuned run is reproducible from its config."""

    context_window: int = 200_000
    always_on_warn_ratio: float = 0.05      # 5% of the window spent before you type
    always_on_fail_ratio: float = 0.15
    top_cost_min_tokens: int = 400          # an always-on asset worth naming individually
    max_description_chars: int = 500
    max_body_tokens: int = 8_000
    min_body_chars: int = 200
    duplicate_similarity: float = 0.85
    stale_days: int = 60
    per_tool_tokens_low: int = 300          # published range for an MCP tool schema
    per_tool_tokens_high: int = 600

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class CheckContext:
    assets: list[Asset]
    workspace: Workspace
    policy: Policy = field(default_factory=Policy)
    counter: Any = None
    usage: dict[str, Any] = field(default_factory=dict)
    probed: bool = False

    def of_kind(self, *kinds: str) -> list[Asset]:
        return [a for a in self.assets if a.kind in kinds]


@runtime_checkable
class Check(Protocol):
    id: str
    title: str

    def run(self, ctx: CheckContext) -> list[Finding]: ...


from .budget import BudgetCheck, McpCostCheck            # noqa: E402
from .duplication import DuplicationCheck                # noqa: E402
from .hygiene import HygieneCheck                        # noqa: E402
from .security import SecurityCheck                      # noqa: E402
from .usage import UsageCheck                            # noqa: E402

CHECKS: list[Check] = [
    BudgetCheck(),
    McpCostCheck(),
    DuplicationCheck(),
    HygieneCheck(),
    UsageCheck(),
    SecurityCheck(),
]

CHECKS_BY_ID = {c.id: c for c in CHECKS}


def run_checks(ctx: CheckContext, only: list[str] | None = None, skip: list[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for c in CHECKS:
        if only and c.id not in only:
            continue
        if skip and c.id in skip:
            continue
        findings += c.run(ctx)
    return findings


__all__ = ["CHECKS", "CHECKS_BY_ID", "Check", "CheckContext", "Policy", "run_checks"]
