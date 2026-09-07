"""What your context costs before you type a word."""

from __future__ import annotations

from ..models import ALWAYS, HIGH, INFO, LOW, MEDIUM, Finding


class BudgetCheck:
    id = "budget"
    title = "Always-on context budget"

    def run(self, ctx) -> list[Finding]:
        p = ctx.policy
        total = sum(a.always_on_tokens for a in ctx.assets)
        ratio = total / p.context_window if p.context_window else 0.0
        sev = (
            HIGH if ratio >= p.always_on_fail_ratio
            else MEDIUM if ratio >= p.always_on_warn_ratio
            else INFO
        )
        out = [
            Finding(
                check=self.id, severity=sev,
                title=f"{total:,} tokens load before your first prompt ({ratio:.1%} of a {p.context_window:,}-token window)",
                detail=(
                    "Every skill catalog line, always-on instruction file and MCP tool schema is "
                    "injected into the system prompt on every request. This is the floor cost of "
                    "your setup: you pay it on the shortest question you ever ask."
                ),
                remediation=(
                    "Start with the highest-cost always-on assets below. Moving content out of an "
                    "always-on file and into an on-demand skill converts a per-request cost into a "
                    "per-use one."
                ),
            )
        ]

        heavy = sorted(
            (a for a in ctx.assets if a.always_on_tokens >= p.top_cost_min_tokens),
            key=lambda a: -a.always_on_tokens,
        )
        for a in heavy[:15]:
            share = a.always_on_tokens / total if total else 0
            always = a.loading == ALWAYS
            out.append(
                Finding(
                    check=self.id,
                    severity=MEDIUM if share >= 0.10 else LOW,
                    title=f"{a.name} costs {a.always_on_tokens:,} always-on tokens ({share:.0%} of your floor)",
                    detail=(
                        f"{a.assistant}/{a.kind}, loading={a.loading}. "
                        + (
                            "The whole file is injected on every request."
                            if always
                            else "Only its catalog entry is always-on, and that entry is unusually large."
                        )
                    ),
                    remediation=(
                        "Split the reference material into an on-demand skill and leave only the rules "
                        "that must apply to every request."
                        if always
                        else "Shorten the description to one sentence that says when to use it, not what it does."
                    ),
                    asset_id=a.id, path=a.path, tokens_at_stake=a.always_on_tokens,
                    at_stake_assets=[a.id],
                )
            )
        return out


class McpCostCheck:
    id = "mcp-cost"
    title = "MCP tool schema cost"

    def run(self, ctx) -> list[Finding]:
        servers = ctx.of_kind("mcp_server")
        if not servers:
            return []
        p = ctx.policy
        out: list[Finding] = []

        unmeasured = [s for s in servers if not s.meta.get("tools_measured")]
        if unmeasured:
            lo = len(unmeasured) * 8 * p.per_tool_tokens_low
            hi = len(unmeasured) * 8 * p.per_tool_tokens_high
            out.append(
                Finding(
                    check=self.id, severity=INFO,
                    title=f"{len(unmeasured)} MCP server(s) have unmeasured tool-schema cost",
                    detail=(
                        "Configuration says these servers exist; it cannot say how many tools they "
                        "publish or how large those schemas are. Published figures put a single tool "
                        f"schema at {p.per_tool_tokens_low}-{p.per_tool_tokens_high} tokens, so at a "
                        f"nominal 8 tools each these would add roughly {lo:,}-{hi:,} tokens — but that "
                        "is an illustration, not a measurement, and is excluded from every total above."
                    ),
                    remediation="Run `contextlint audit --mcp-probe` to measure the real schemas. "
                                "Probing starts each server, so read the pre-flight list first.",
                    refs=[s.name for s in unmeasured],
                )
            )

        for s in servers:
            if not s.meta.get("tools_measured"):
                continue
            n = s.meta.get("tool_count") or 0
            if s.always_on_tokens >= p.top_cost_min_tokens:
                out.append(
                    Finding(
                        check=self.id,
                        severity=HIGH if s.always_on_tokens > 5000 else MEDIUM,
                        title=f"MCP server '{s.name}' publishes {n} tools costing {s.always_on_tokens:,} tokens every turn",
                        detail=(
                            "Measured from a live `tools/list` response. Tool schemas are injected on "
                            "every request whether or not you use the server, and tool-selection "
                            "accuracy degrades as the tool count grows."
                        ),
                        remediation=(
                            "Disable this server in projects that do not need it, or move it behind a "
                            "tool-search/deferred-loading mechanism if your client supports one."
                        ),
                        asset_id=s.id, path=s.path, tokens_at_stake=s.always_on_tokens,
                        at_stake_assets=[s.id],
                    )
                )
        return out
