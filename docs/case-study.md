# Case study: auditing a 92-skill, 5-server setup

Run on the author's own machine, 2026-09-07, with `contextlint audit --mcp-probe`. Every figure
below came out of the tool. Nothing is rounded in the tool's favour.

## The setup

A single Obsidian vault used as a Claude Code workspace across ~30 side projects, accumulated
over roughly four months without ever being audited.

| | |
|---|---|
| `SKILL.md` files across four roots | 92 |
| Skill markdown on disk | 1.37 MB |
| Memory and instruction files | 46 |
| MCP servers configured | 5 |
| Sessions in transcript history | 148 over 16 days |

## What it cost

```
ALWAYS-ON CONTEXT
  18,703 tokens   9.4% of a 200,000-token window
  on-demand (loaded only when invoked): 271,820 tokens
```

Nearly one tenth of the window was spent before typing anything. The split matters more than
the total: 271,820 tokens of skill bodies are **not** an always-on cost — they arrive only when
a skill is invoked. Pricing them as always-on, which is what auditing by file size does, would
have reported a 145.3% context overhead and been wrong by a factor of 15.5.

| Source | Always-on tokens | Share |
|---|---|---|
| Skills (catalog entries only) | 9,189 | 49% |
| MCP tool schemas | 5,216 | 28% |
| Memory files | 4,223 | 23% |
| Instruction files (`AGENTS.md`) | 75 | <1% |

## What the session logs said

The transcripts are the part static analysis cannot reach.

> **77 of 92 installed skills were never invoked in 148 recorded sessions.**
> 31 distinct skills were invoked across the whole history. The other 61 exist, cost a catalog
> entry on every request, and have never once been chosen.

That is a finding, not a verdict. A skill can go unused because it is badly described rather
than because it is useless — and one of the never-invoked skills turned out to be a genuinely
rare, genuinely important one. The report says so explicitly instead of recommending deletion.

## What the MCP probe found

Static config listed five servers. It could not say what they cost, and the answer was not
guessable:

| Server | Tools | Tokens/turn | Ever called in 148 sessions |
|---|---|---|---|
| `github` | 26 | 3,517 | yes |
| `filesystem` | 14 | 1,699 | **never** |
| `n8n` | — | — | **never** (server fails to start) |
| `make` | — | — | **never** (server fails to start) |
| `pixelcut` | — | — | **never** (HTTP 401) |

1,699 tokens per request, forever, for a server that has never been called once. Three more
servers that do not work at all — two failing to respond to `tools/list`, one returning 401 —
were still being launched every session, each via an unpinned `npx -y`.

Nothing in the static configuration hinted at any of this. The tool count only exists on the
wire, and the usage record only exists in the transcripts.

## What it found in the config

| | |
|---|---|
| Byte-identical duplicate skills | 12 pairs, across `.claude/skills/` and `.agents/skills/` |
| Skills with no YAML frontmatter | 6 |
| Findings at high severity | 18 |
| Findings at medium severity | 68 |

The six frontmatter-less skills were the most interesting failure. They still appeared in the
skill catalog — the assistant had silently fallen back to using the first ~200 characters of the
body as the description. So they were being paid for on every request, and what was being paid
for was a truncated mid-sentence prose fragment that had never been written to help a model
decide anything.

## What was actually recoverable

```
safe to reclaim    1,310 tok (10%)  duplicates and empty assets — removing them cannot change behaviour
worth reviewing   16,502 tok (88%)  needs judgement — see the findings
```

Two numbers, never summed. The honest headline is **10%, immediately and safely** — the
duplicates. The larger figure is what is *sitting behind decisions*: 61 unused skills, an
uncalled filesystem server, three dead servers. Every one of those is a judgement, and
presenting them as available savings is how this field arrived at its 90% claims.

Adding the two together would have produced a "98% reduction available" headline. It would also
have been meaningless.

## Method

```bash
uvx contextlint --mcp-probe --html report.html
```

Token counts from the offline heuristic, whose out-of-sample aggregate error against `tiktoken`
o200k_base is +1.05% over 541 files (`benchmarks/calibrate.py`). MCP figures measured from live
`tools/list` responses. Usage figures parsed from local transcripts — tool names and timestamps
only, no prompt or response content, nothing transmitted anywhere.
