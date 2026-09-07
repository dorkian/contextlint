"""The audit pipeline: discover, price, correlate, check."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from . import __version__, usage as usage_mod
from .adapters import ADAPTERS, ADAPTERS_BY_NAME
from .checks import CheckContext, Policy, run_checks
from .discovery import Workspace
from .models import Report, dedupe_assets
from .tokens import get_counter, price


def run_audit(
    path: str | None = None,
    *,
    assistants: list[str] | None = None,
    include_global: bool = True,
    tokenizer: str = "heuristic",
    policy: Policy | None = None,
    use_usage: bool = True,
    session_logs: list[Path] | None = None,
    mcp_probe: bool = False,
    probe_timeout: float = 20.0,
    probe_servers: list[str] | None = None,
    probe_no_network: bool = False,
    only_checks: list[str] | None = None,
    skip_checks: list[str] | None = None,
    on_probe: Callable[[str, str], None] | None = None,
) -> Report:
    started = time.time()
    ws = Workspace.resolve(path, include_global=include_global)
    policy = policy or Policy()

    selected = (
        [ADAPTERS_BY_NAME[a] for a in assistants if a in ADAPTERS_BY_NAME]
        if assistants else ADAPTERS
    )

    assets, detected = [], []
    for adapter in selected:
        if not adapter.detect(ws):
            continue
        detected.append(adapter.name)
        assets += adapter.collect(ws)
    assets = dedupe_assets(assets)

    counter = get_counter(tokenizer)

    if mcp_probe:
        _probe_servers(assets, counter, probe_timeout, on_probe,
                        only=probe_servers, no_network=probe_no_network)

    price(assets, counter)

    stats = None
    if use_usage:
        roots = session_logs or usage_mod.default_log_roots(ws.home)
        stats = usage_mod.collect(roots)

    ctx = CheckContext(
        assets=assets, workspace=ws, policy=policy, counter=counter,
        usage={"stats": stats}, probed=mcp_probe,
    )
    findings = run_checks(ctx, only=only_checks, skip=skip_checks)

    return Report(
        assets=assets,
        findings=findings,
        meta={
            "version": __version__,
            "project": str(ws.project),
            "home": str(ws.home),
            "include_global": include_global,
            "assistants_detected": detected,
            "tokenizer": tokenizer,
            "tokenizer_exact": tokenizer in ("tiktoken", "anthropic"),
            "mcp_probed": mcp_probe,
            "policy": policy.__dict__,
            "usage": stats.to_dict() if stats else {"available": False},
            "elapsed_seconds": round(time.time() - started, 2),
        },
    )


def _probe_servers(assets, counter, timeout, on_probe, *, only=None, no_network=False) -> None:
    from .mcp_probe import probe  # imported here so a non-probing run never touches subprocess

    wanted = set(only) if only else None
    for a in assets:
        if a.kind != "mcp_server":
            continue
        if wanted is not None and a.name not in wanted:
            continue
        if no_network and not (a.meta.get("transport") == "stdio" or a.meta.get("command")):
            a.meta["probe_error"] = "skipped: --no-network (server reached over the network)"
            continue
        if on_probe:
            on_probe(a.name, _describe(a))
        result = probe(a.meta, a.name, timeout)
        if not result.ok:
            a.meta["probe_error"] = result.error
            continue
        a.always_on_text = result.schema_text
        a.meta.update(
            tools_measured=True,
            tool_count=len(result.tools),
            tool_names=[t.get("name") for t in result.tools],
            tool_descriptions=[t.get("description", "") for t in result.tools],
        )


def _describe(asset) -> str:
    from .mcp_probe import describe

    return describe(asset.meta)
