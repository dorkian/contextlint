"""Assets that are present but malformed, and therefore cost without paying."""

from __future__ import annotations

from ..models import ALWAYS, CERTAIN, HIGH, LOW, MEDIUM, Finding


class HygieneCheck:
    id = "hygiene"
    title = "Asset hygiene"

    def run(self, ctx) -> list[Finding]:
        out: list[Finding] = []
        p = ctx.policy

        for a in ctx.assets:
            m = a.meta

            if m.get("missing_frontmatter") and a.kind in ("skill", "agent", "command"):
                out.append(
                    Finding(
                        check=self.id, severity=HIGH,
                        title=f"{a.kind} '{a.name}' has no YAML frontmatter",
                        detail=(
                            "Without a `name:` and `description:` block the assistant falls back to a "
                            "prefix of the body as the catalog entry. You are still paying for a catalog "
                            "line — you are just paying for a truncated sentence that was never written "
                            "to help the model decide when to load this."
                        ),
                        remediation="Add `---\\nname: <slug>\\ndescription: <when to use this>\\n---` at the top of the file.",
                        asset_id=a.id, path=a.path,
                    )
                )
            elif m.get("missing_description"):
                out.append(
                    Finding(
                        check=self.id, severity=MEDIUM,
                        title=f"{a.kind} '{a.name}' has frontmatter but no description",
                        detail="The catalog entry falls back to a body prefix, which is what the model "
                               "reads when deciding whether to load this asset.",
                        remediation="Add a one-sentence `description:` that states the trigger, not the contents.",
                        asset_id=a.id, path=a.path,
                    )
                )

            desc = str(m.get("description") or "")
            if len(desc) > p.max_description_chars:
                excess = a.always_on_tokens - (a.always_on_tokens * p.max_description_chars // max(len(desc), 1))
                out.append(
                    Finding(
                        check=self.id, severity=MEDIUM,
                        title=f"{a.kind} '{a.name}' has a {len(desc):,}-character description",
                        detail=(
                            f"Descriptions are always-on. This one is {len(desc) / p.max_description_chars:.1f}x "
                            f"the {p.max_description_chars}-character guideline, and every character is "
                            "injected on every request in every session forever."
                        ),
                        remediation="Cut it to one or two sentences naming the trigger. Move the "
                                    "examples and caveats into the body, which loads on demand.",
                        asset_id=a.id, path=a.path, tokens_at_stake=max(excess, 0),
                        at_stake_assets=[a.id],
                    )
                )

            if a.on_demand_tokens > p.max_body_tokens:
                out.append(
                    Finding(
                        check=self.id, severity=LOW,
                        title=f"{a.kind} '{a.name}' has a {a.on_demand_tokens:,}-token body",
                        detail=(
                            "This is not an always-on cost, but it is what lands in the window the "
                            "moment the asset is invoked, and it competes with the actual task."
                        ),
                        remediation="Split reference material into files the skill reads when it needs them.",
                        asset_id=a.id, path=a.path,
                    )
                )

            if a.kind in ("skill", "agent", "command") and len((a.on_demand_text or "").strip()) < 50:
                out.append(
                    Finding(
                        check=self.id, severity=MEDIUM,
                        title=f"{a.kind} '{a.name}' is effectively empty",
                        detail="The body is under 50 characters, so this asset costs a catalog entry "
                               "and delivers nothing when loaded.",
                        remediation="Write it or delete it.",
                        asset_id=a.id, path=a.path, tokens_at_stake=a.always_on_tokens,
                        at_stake_assets=[a.id], confidence=CERTAIN, fixable=True, fix_hint={"action": "delete", "paths": [str(a.path)]},
                    )
                )

            if a.loading == ALWAYS and a.kind in ("memory", "instruction") and a.always_on_tokens > 3000:
                out.append(
                    Finding(
                        check=self.id, severity=MEDIUM,
                        title=f"always-on file '{a.name}' is {a.always_on_tokens:,} tokens",
                        detail="Instruction and memory files at this size are usually part rules and "
                               "part reference. Only the rules need to be always-on.",
                        remediation="Keep the rules the model must never violate; move the reference "
                                    "material into an on-demand skill it can read when relevant.",
                        asset_id=a.id, path=a.path,
                        tokens_at_stake=a.always_on_tokens // 2,
                        at_stake_assets=[a.id],
                    )
                )
        return out
