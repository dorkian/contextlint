# contextlint

Audit what your AI coding assistant loads **before you type a word** — token cost, dead weight, and MCP security risk — across Claude Code, Codex/AGENTS.md, Cursor and GitHub Copilot.

```bash
uvx contextlint
```

Read-only by default. No API key, no network, no telemetry, no dependencies.

---

## Why

Every skill, instruction file and MCP tool schema your assistant loads is injected into the system prompt before your first message. You pay for it on every request, including the ones where none of it is relevant. That cost is invisible: it lives in four different config formats across two directory trees, and nothing shows you the total.

Existing tools measure the wrong thing. They price a skill by its size on disk. But a well-formed skill's body only loads when it is invoked — what you pay every turn is its one-line catalog entry. Conflating the two overstates the recoverable savings by an order of magnitude, which is how this space ended up full of unreproducible "90% reduction" claims.

contextlint separates the two, prices them independently, and refuses to add numbers together that mean different things.

## What it does that other tools don't

**It reads your session history.** Static analysis can tell you a skill is large. Only the transcripts can tell you that in 147 sessions you invoked 31 distinct skills out of 92 installed. Those two facts lead to opposite actions, so contextlint reads both. Nothing leaves your machine — only tool-invocation names and timestamps are parsed, never prompt or response text.

**It treats MCP security as a first-class check.** Unauthenticated remote servers, plaintext credentials in config, unpinned `npx -y` supply chains, shell-launched servers, filesystem servers rooted at `/`, and instruction-shaped text hidden in tool descriptions — including zero-width and Unicode-tag characters that render as nothing to you and as text to the model.

**It separates what's certain from what's a judgement call.** Deleting a byte-identical duplicate cannot change behaviour. Deleting a skill you haven't invoked in 90 days might. These are reported as two numbers and never summed.

**Its numbers have a command attached.** `python benchmarks/run.py` reproduces every figure below on your machine.

## Example

```
contextlint  /Users/you/project
────────────────────────────────────────────────────────────────────────────
assistants  claude_code, codex, cursor
assets      146   tokenizer heuristic (estimate)   9.06s

ALWAYS-ON CONTEXT
  ██·····································   13,487 tok   6.7% of 200,000
  on-demand (loaded only when invoked): 271,820 tok
  safe to reclaim    1,310 tok (10%)  duplicates and empty assets — removing them cannot change behaviour
  worth reviewing   11,286 tok (84%)  needs your judgement — see the findings below

REAL USAGE
  147 sessions over 16 days   31 distinct skills invoked
  most used: no-ai-slop (24x), cv-humanizer (15x), job (9x)

FINDINGS   CRIT 0  HIGH 18  MED 65  LOW 11  INFO 2

 HIGH  'humanizer' is byte-identical in 2 locations  -178 tok
       Identical content: .claude/skills/humanizer/SKILL.md, .agents/skills/humanizer/SKILL.md.
       Each copy contributes its own catalog entry, and the copies will drift apart the
       first time one is edited.
       → Keep .claude/skills/humanizer/SKILL.md and delete the other copy.
```

`--html report.html` writes a self-contained visual report: a treemap of always-on cost coloured by whether you have ever invoked the asset, a cost-against-usage scatter, and filterable findings. One file, no CDN, works offline, respects your system theme.

## Install

```bash
uvx contextlint                 # no install
pipx install contextlint        # or install it
pip install contextlint[exact]  # + tiktoken, for measured rather than estimated counts
```

Python 3.10+. Zero required dependencies.

## Usage

```bash
contextlint                            # audit this project + your global config
contextlint --html report.html         # visual report
contextlint --format json              # machine-readable
contextlint --assistant cursor         # one assistant only
contextlint --no-global                # this project only
contextlint --tokenizer tiktoken       # exact counts
contextlint --fail-on high             # exit 1 in CI when something serious is found
contextlint --mcp-probe                # measure real MCP tool schemas (starts your servers)
contextlint checks                     # list adapters and checks
contextlint fix                        # print a plan; changes nothing
contextlint fix --apply                # apply it, with a backup and an undo script
```

### MCP tool schemas are unmeasured by default

Configuration says a server exists. It cannot say the server publishes 41 tools whose schemas cost 12,000 tokens on every turn — that number only exists on the wire. So by default contextlint counts servers, reports their schema cost as *unmeasured*, and excludes it from the totals rather than inventing a per-tool average.

`--mcp-probe` measures it properly: it runs the MCP handshake against each server and prices the real `tools/list` response. It starts your servers to do that, so it prints exactly what it is about to run and asks first.

### `fix` is deliberately timid

It only removes what is provably safe: byte-identical duplicates and empty assets. Everything else needs your judgement and stays in the report.

It prints a plan and changes nothing without `--apply`. It refuses to run on a dirty git tree, so `git checkout .` is always a valid undo. And it copies every removed file into `.contextlint-backups/<timestamp>/` with a generated `restore.sh`, so the undo works outside git too.

## What it parses

| Assistant | Sources |
|---|---|
| Claude Code | `.claude/skills/*/SKILL.md`, `.agents/skills/`, plugin skills, `.claude/agents/`, `.claude/commands/`, the `CLAUDE.md` chain, auto-memory files, `.mcp.json`, `settings.json` permissions and hooks |
| Codex / AGENTS.md | `AGENTS.md` at root and nested, `~/.codex/config.toml` MCP servers |
| Cursor | `.cursor/rules/*.mdc` (respecting `alwaysApply` vs `globs`), `.cursorrules`, `.cursor/mcp.json` |
| GitHub Copilot | `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` (respecting `applyTo`), `.github/prompts/` |

Loading mode is tracked per asset — `always`, `on_demand`, `conditional`, `deferred` — because that, not file size, is what determines cost.

## Checks

| id | What it looks for |
|---|---|
| `budget` | Total always-on cost, share of the context window, the assets driving it |
| `mcp-cost` | Real tool-schema cost per MCP server (with `--mcp-probe`) |
| `duplication` | Byte-identical copies, same-name shadowing, near-duplicates |
| `hygiene` | Missing frontmatter or description, oversized descriptions, empty and bloated assets |
| `usage` | Installed but never invoked; stale; MCP servers never called |
| `security` | Unauthenticated and plaintext-HTTP servers, credentials in config, unpinned supply chains, shell launches, filesystem scope creep, tool-poisoning and hidden-character patterns, blanket permission rules |

## Reproducing the numbers

```bash
python benchmarks/run.py                                              # detection + savings
uv run --no-project --with tiktoken python benchmarks/calibrate.py    # tokenizer error
uv run --no-project --with tiktoken python benchmarks/tune.py         # refit the heuristic
```

Measured on this repository at the version you are reading:

| Measurement | Result | How |
|---|---|---|
| Planted defects detected | **15 / 15** | `benchmarks/run.py`, against `benchmarks/fixtures/bloated` |
| Savings from automatic fixes | **14.0%** of always-on tokens | before/after audit of a fixture copy, real `fix` path |
| Heuristic tokenizer, aggregate error | **+1.05%** | vs `tiktoken` o200k_base over 541 files / 1,007,941 tokens |
| Heuristic tokenizer, median per-file | **3.79%** | same corpus |
| Heuristic tokenizer, p90 per-file | **10.00%** | same corpus |
| Held-out error after fitting | **+2.82%** aggregate, 3.90% median | fitted on half the corpus, measured on the other half |

The 14% is small on purpose. It is what an automatic, behaviour-preserving fix actually recovers. The larger number — the assets you have never invoked — is reported separately and left to you, because deleting them is a decision, not an optimisation.

### About the tokenizer

The default counter is an offline approximation: a GPT-style pre-tokenizer plus per-character-class length rules, with seven parameters fitted against `tiktoken`. It ships with the parameters fitted on **half** the corpus so the published error is genuinely out-of-sample.

It is calibrated on agent configuration — markdown, JSON schemas, YAML frontmatter — and its error on other kinds of text is unmeasured. For exact counts use `--tokenizer tiktoken`, or `--tokenizer anthropic` for a specific Claude model via the free `count_tokens` endpoint (opt-in; it sends your config text to the API, which is why it is not the default).

## Privacy

The default path reads local files, makes no network connection, and writes nothing. `--mcp-probe` starts your configured servers and asks first. `--tokenizer anthropic` is the only mode that transmits your content anywhere, and it is opt-in.

## Design notes

- **One adapter per assistant, one file per check.** Adding an assistant is one file and one list entry.
- **No required dependencies.** A tool whose thesis is that dependencies have a cost should demonstrate that it believes it.
- **Findings are signals, not verdicts.** Every security finding names the pattern it matched and why, so you can dismiss it in ten seconds when it is wrong.
- **Never claim a percentage the harness can't reproduce.**

## Related work

Four Claude Code token optimizers exist ([valorisa/Claude-Skills](https://github.com/valorisa/Claude-Skills), [Sharan0516/claude-token-optimizer](https://github.com/Sharan0516/claude-token-optimizer), [4pixeltechBR/token_saver_ClaudeCode](https://github.com/4pixeltechBR/token_saver_ClaudeCode), [KINGSTAR-OMEGA/claude-token-optimizer](https://github.com/KINGSTAR-OMEGA/claude-token-optimizer)), and a separate cluster of MCP security scanners. contextlint sits in the gap between them: cross-assistant, usage-correlated, security-aware, and reproducible. Sharan0516's router pattern — replacing always-loaded descriptions with a lightweight catalog — is the strongest idea in the existing field and directly informed how loading modes are modelled here.

## Licence

MIT
