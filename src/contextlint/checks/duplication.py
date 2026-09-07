"""Two copies of the same skill cost twice and disagree eventually."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher

from ..models import CERTAIN, HIGH, LOW, MEDIUM, Finding


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class DuplicationCheck:
    id = "duplication"
    title = "Duplicate and shadowed assets"

    def run(self, ctx) -> list[Finding]:
        out: list[Finding] = []
        assets = [a for a in ctx.assets if a.kind in ("skill", "agent", "command", "rule")]

        # --- byte-identical bodies in more than one place -----------------------
        by_hash: dict[str, list] = defaultdict(list)
        for a in assets:
            body = _norm(a.on_demand_text or a.always_on_text)
            if len(body) < ctx.policy.min_body_chars:
                continue
            by_hash[hashlib.sha256(body.encode()).hexdigest()].append(a)

        duplicated_ids: set[str] = set()
        for group in by_hash.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda a: str(a.path))
            keep, extra = group[0], group[1:]
            reclaimable = sum(a.always_on_tokens for a in extra)
            duplicated_ids.update(a.id for a in extra)
            out.append(
                Finding(
                    check=self.id, severity=HIGH,
                    title=f"'{keep.name}' is byte-identical in {len(group)} locations",
                    detail=(
                        "Identical content: "
                        + ", ".join(str(a.path) for a in group)
                        + ". Each copy contributes its own catalog entry, and the copies will drift "
                        "apart the first time one is edited."
                    ),
                    remediation=(
                        f"Keep {keep.path} and delete the other {len(extra)} "
                        f"cop{'y' if len(extra) == 1 else 'ies'}, or replace them with a symlink."
                    ),
                    asset_id=keep.id, path=keep.path, tokens_at_stake=reclaimable,
                    at_stake_assets=[a.id for a in extra], confidence=CERTAIN,
                    refs=[str(a.path) for a in extra],
                    fixable=True,
                    fix_hint={"action": "delete", "paths": [str(a.path) for a in extra],
                              "keep": str(keep.path)},
                )
            )

        # --- same name in two roots: one silently shadows the other -------------
        by_name: dict[tuple[str, str, str], list] = defaultdict(list)
        for a in assets:
            by_name[(a.assistant, a.kind, a.name)].append(a)
        for (assistant, kind, name), group in by_name.items():
            if len(group) < 2 or all(a.id in duplicated_ids for a in group[1:]):
                continue
            out.append(
                Finding(
                    check=self.id, severity=MEDIUM,
                    title=f"{kind} '{name}' is defined {len(group)} times with different content",
                    detail=(
                        "Same name, different bodies: "
                        + "; ".join(f"{a.path} ({a.on_demand_tokens:,} tok)" for a in group)
                        + ". Which one wins depends on load order, so the behaviour you get is "
                        "whichever copy the assistant happened to read last."
                    ),
                    remediation="Rename one, or consolidate them into a single definition.",
                    asset_id=group[0].id, path=group[0].path,
                    tokens_at_stake=sum(a.always_on_tokens for a in group[1:]),
                    at_stake_assets=[a.id for a in group[1:]],
                    refs=[str(a.path) for a in group],
                )
            )

        # --- near-duplicates ----------------------------------------------------
        candidates = [
            a for a in assets
            if a.id not in duplicated_ids
            and len(_norm(a.on_demand_text)) >= ctx.policy.min_body_chars
        ]
        candidates.sort(key=lambda a: -len(a.on_demand_text))
        threshold = ctx.policy.duplicate_similarity
        reported: set[str] = set()
        for i, a in enumerate(candidates[:200]):
            if a.id in reported:
                continue
            na = _norm(a.on_demand_text)
            for b in candidates[i + 1: i + 60]:
                if b.id in reported:
                    continue
                nb = _norm(b.on_demand_text)
                # cheap length gate before the expensive ratio
                if min(len(na), len(nb)) / max(len(na), len(nb)) < threshold:
                    continue
                ratio = SequenceMatcher(None, na, nb).quick_ratio()
                if ratio < threshold:
                    continue
                ratio = SequenceMatcher(None, na, nb).ratio()
                if ratio < threshold:
                    continue
                reported.add(b.id)
                out.append(
                    Finding(
                        check=self.id, severity=LOW,
                        title=f"'{a.name}' and '{b.name}' are {ratio:.0%} identical",
                        detail=f"{a.path}\n{b.path}",
                        remediation="Merge them, or make the descriptions state clearly when each applies "
                                    "— near-identical siblings make the model's choice arbitrary.",
                        asset_id=b.id, path=b.path, tokens_at_stake=b.always_on_tokens,
                        at_stake_assets=[b.id],
                    )
                )
        return out
