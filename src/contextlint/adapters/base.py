"""Adapter contract. One file per assistant, no shared special-casing."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..discovery import Workspace
from ..models import Asset


@runtime_checkable
class Adapter(Protocol):
    name: str          # machine id, e.g. "claude_code"
    label: str         # human label, e.g. "Claude Code"

    def detect(self, ws: Workspace) -> bool:
        """True when this assistant is configured anywhere in the workspace."""

    def collect(self, ws: Workspace) -> list[Asset]:
        """Every asset this assistant loads, normalised."""


def catalog_line(name: str, description: str) -> str:
    """The one line an assistant injects per on-demand asset.

    This is the whole reason contextlint's numbers differ from every other
    auditor's: a skill's always-on cost is this line, not its body.
    """
    return f"- {name}: {description}\n"
