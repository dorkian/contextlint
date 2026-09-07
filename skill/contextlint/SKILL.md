---
name: contextlint
description: Audit this project's AI-assistant configuration for always-on token cost, never-invoked skills, duplicate or shadowed skills, and MCP security risk. Use when the user asks why their context window is full, why the assistant is slow or expensive, which skills are dead weight, whether their MCP servers are safe, or asks to clean up or audit .claude / .cursor / .github / AGENTS.md configuration.
allowed-tools: Bash, Read
---

# contextlint

Runs the `contextlint` CLI and interprets the result. The CLI does the measuring; this skill
decides what to do about it.

## Run

```bash
uvx contextlint --format json
```

Add `--html /tmp/contextlint.html` when the user would benefit from the visual report (treemap
of always-on cost, cost-against-usage scatter, filterable findings).

If `uvx` is unavailable, fall back to `pipx run contextlint` or `python -m contextlint`.

## Reading the output

- `totals.always_on_tokens` is the floor cost: paid on every request, before the user types.
- `totals.on_demand_tokens` is *not* added to it. It is what arrives when an asset is invoked.
- `totals.certain_tokens` is safe to reclaim — duplicates and empty assets, no behaviour change.
- `totals.candidate_tokens` needs the user's judgement. Never present it as available savings.
- `meta.usage.available` false means dead-weight detection did not run; say so rather than
  implying the skills are all in use.
- `meta.mcp_probed` false means MCP tool-schema cost is **excluded** from the totals. The real
  number is usually larger. Offer `--mcp-probe`, and mention it starts their servers.

## Presenting it

Lead with the always-on total and its share of the window. Then the certain savings. Then the
top three findings by severity, each with its concrete remediation.

Do not report `candidate_tokens` and `certain_tokens` as one figure. Do not quote a percentage
saving the user has not actually applied yet.

## Acting on it

`contextlint fix` prints a plan and changes nothing. Show the plan and let the user decide.
`contextlint fix --apply` needs a clean git tree and writes a backup with a `restore.sh`.

For findings that are not auto-fixable — a skill with no frontmatter, an over-long description,
a never-invoked skill — offer to edit the specific file. Never bulk-delete skills on the basis
of the never-invoked list: it is a prompt to review, and a rarely-used skill can be the one that
matters most when it fires.

Security findings are heuristics over configuration, not proof of a vulnerability. Report the
matched pattern and let the user judge.
