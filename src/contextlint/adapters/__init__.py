"""Adapter registry. Adding an assistant is one import and one list entry."""

from __future__ import annotations

from .base import Adapter, catalog_line
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .copilot import CopilotAdapter
from .cursor import CursorAdapter

ADAPTERS: list[Adapter] = [
    ClaudeCodeAdapter(),
    CodexAdapter(),
    CursorAdapter(),
    CopilotAdapter(),
]

ADAPTERS_BY_NAME = {a.name: a for a in ADAPTERS}

__all__ = ["ADAPTERS", "ADAPTERS_BY_NAME", "Adapter", "catalog_line"]
