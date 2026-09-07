"""Installed but never invoked: the only honest definition of dead weight."""

from __future__ import annotations

from ..models import INFO, LOW, MEDIUM, Finding


class UsageCheck:
    id = "usage"
    title = "Real usage correlation"

    def run(self, ctx) -> list[Finding]:
        stats = ctx.usage.get("stats")
        if stats is None or not getattr(stats, "available", False):
            return [
                Finding(
                    check=self.id, severity=INFO,
                    title="No session history found — dead-weight detection is disabled",
                    detail=(
                        "Without transcripts, contextlint can only tell you what an asset costs, not "
                        "whether you have ever used it. Those two facts lead to opposite decisions."
                    ),
                    remediation="Run against a machine with `~/.claude/projects` present, or pass "
                                "`--session-logs <dir>`.",
                )
            ]

        out: list[Finding] = []
        skills = [a for a in ctx.assets if a.kind in ("skill", "agent", "command")]
        invoked = set(stats.skills)
        never = [a for a in skills if a.name not in invoked]
        span = stats.span_days

        if never:
            reclaimable = sum(a.always_on_tokens for a in never)
            sample = ", ".join(sorted(a.name for a in never)[:12])
            out.append(
                Finding(
                    check=self.id, severity=MEDIUM,
                    title=(
                        f"{len(never)} of {len(skills)} installed skills were never invoked "
                        f"in {stats.sessions} recorded sessions"
                    ),
                    detail=(
                        f"History spans {span:.0f} days and contains {len(invoked)} distinct invoked "
                        f"skills. Never invoked: {sample}"
                        + (f", +{len(never) - 12} more" if len(never) > 12 else "")
                        + ". Read this as a prompt to look, not as a verdict: a skill can be unused "
                        "because it is badly described, or because it is genuinely rare and genuinely "
                        "important when it fires."
                    ),
                    remediation=(
                        f"Reclaims about {reclaimable:,} always-on tokens if all were removed. Triage "
                        "them: rewrite the description if the skill is good but never selected, delete "
                        "it if you have not wanted it in "
                        f"{span:.0f} days."
                    ),
                    tokens_at_stake=reclaimable,
                    at_stake_assets=[a.id for a in never],
                    refs=sorted(a.name for a in never),
                )
            )

        for a in skills:
            days = stats.days_since(a.name)
            if days is not None and days > ctx.policy.stale_days:
                out.append(
                    Finding(
                        check=self.id, severity=LOW,
                        title=f"skill '{a.name}' last used {days:.0f} days ago",
                        detail=f"Invoked {stats.skills[a.name]['count']}x total, none recently.",
                        remediation="Keep if seasonal, delete if superseded.",
                        asset_id=a.id, path=a.path, tokens_at_stake=a.always_on_tokens,
                        at_stake_assets=[a.id],
                    )
                )

        # --- MCP servers configured but never called ---------------------------
        used_servers = set(stats.mcp_servers)
        for s in ctx.of_kind("mcp_server"):
            if any(s.name == u or s.name in u or u in s.name for u in used_servers):
                continue
            out.append(
                Finding(
                    check=self.id, severity=MEDIUM,
                    title=f"MCP server '{s.name}' was never called in {stats.sessions} sessions",
                    detail=(
                        "Its tool schemas are injected on every request regardless. Note that clients "
                        "which rename connectors (opaque ids rather than config names) can defeat this "
                        "match, so confirm before removing."
                    ),
                    remediation="Remove it from this project's MCP config, or scope it to the projects "
                                "that actually use it.",
                    asset_id=s.id, path=s.path, tokens_at_stake=s.always_on_tokens,
                    at_stake_assets=[s.id],
                )
            )
        return out
