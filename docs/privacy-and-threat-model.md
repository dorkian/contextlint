# Privacy & Threat Model

`contextlint` is designed as an offline-by-default, inspectable developer tool. It evaluates what an AI coding assistant loads into its context window, audits configuration security, and identifies unused assets.

Because it inspects your development environment and configuration files, this document specifies **exactly what contextlint reads, executes, stores, and transmits**.

---

## 1. What contextlint reads

`contextlint` operates exclusively within the target project directory and the user's home directory (`~`). It never traverses outside these boundaries.

### Exact configuration sources inspected, per assistant

| Assistant | Files & Locations Inspected |
|---|---|
| **Claude Code** | `.claude/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md`, `.claude/plugins/`, `.claude/agents/*.md`, `.claude/commands/*.md`, `CLAUDE.md` chain (root and project subdirectories), `.claude/projects/*/memory/MEMORY.md`, `.mcp.json`, `.claude.json` (root and `projects.<path>.mcpServers`), `.claude/settings.json`, `.claude/settings.local.json`. |
| **Codex / AGENTS.md** | `AGENTS.md` (project root and project subdirectories), `~/.codex/config.toml` (`[mcp_servers]` table). |
| **Cursor** | `.cursor/rules/*.mdc` (inspecting `alwaysApply` vs `globs`), `.cursorrules`, `.cursor/mcp.json`. |
| **GitHub Copilot** | `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` (inspecting `applyTo`), `.github/prompts/`. |

### Session transcript analysis

When session history is available (e.g. `~/.claude/projects/`), `contextlint` inspects transcripts to correlate always-on asset cost with real usage.

- **What is extracted**: Only tool-invocation names, skill names, and invocation timestamps.
- **What is NEVER extracted or read**: User prompts, assistant responses, source code diffs, file contents, or conversation tokens.
- **Opt-out**: Pass `--no-usage` (or `--no-global` to limit scope to the current project only) to skip reading session transcripts entirely.

---

## 2. What contextlint executes

By default, **`contextlint audit` executes zero external commands or third-party code**. It performs purely static analysis over markdown, JSON, and TOML configuration files.

### The one execution exception: `--mcp-probe`

MCP tool schemas are dynamic: a configuration file declares that a server exists, but the schemas of the tools it exposes exist only over the JSON-RPC wire.

- `--mcp-probe` starts each configured MCP server (via its configured command or HTTP endpoint) and runs the MCP `tools/list` handshake to measure real tool schema sizes.
- **Defensive guards**:
  - Requires explicit opt-in via `--mcp-probe`.
  - Prompts for interactive confirmation on a TTY before starting any process, printing the exact server name and command line to be executed.
  - Can be run with `--probe-timeout` (default 20 seconds).

---

## 3. What contextlint stores

`contextlint audit` is strictly read-only and writes nothing to disk.

### File write operations

Only two commands write files:

1. **`contextlint fix --apply`**:
   - Refuses to run if the working tree is dirty (unless overridden with `--allow-dirty`), ensuring `git checkout .` remains a guaranteed undo.
   - Saves a restorable backup into `.contextlint-backups/<timestamp>/` containing removed files and a manifest.
   - Supports platform-agnostic restoration via `contextlint restore <backup-dir>`.
2. **`contextlint watch`**:
   - Appends audit snapshot metadata (aggregates and finding fingerprints) to `.contextlint-history.jsonl` in the project root to compute drift between runs.
   - Never writes asset content, prompts, or sensitive strings to the history file.

---

## 4. What contextlint transmits

**By default, contextlint transmits zero bytes over the network.**

- No telemetry.
- No analytics.
- No error-reporting pingbacks.
- No remote license checks.

### The one transmission exception: `--tokenizer anthropic`

The default tokenizer runs offline using contextlint's built-in heuristic (or exact `tiktoken` when `--tokenizer tiktoken` is used).

- Passing `--tokenizer anthropic` sends configuration text to the Anthropic `count_tokens` API endpoint to measure exact tokenization for specific Claude model families.
- This requires an API key and is strictly opt-in.

---

## 5. Security findings scope and non-guarantee

Contextlint identifies known high-risk configuration patterns (e.g. plaintext credentials in argv/environment variables, plaintext HTTP transport, root filesystem scoping, unpinned package chains, invisible characters).

> [!CAUTION]
> **Non-Guarantee**: Contextlint is not a penetration test, does not verify server implementation safety, and cannot guarantee that an MCP server, tool description, or agent workflow is safe or uncompromised. It audits static configuration declarations.

### Findings certainty classes

| Class | Meaning | Examples |
|---|---|---|
| **Certain** | Factual, deterministic configuration reality | Plaintext HTTP transport URL, credentials passed in argv, shell launch wrappers, root `/` path exposure, byte-identical duplicate files. |
| **Review / Heuristic** | Pattern match requiring human judgment | Instruction-shaped tool descriptions, Unicode-tag / zero-width characters, oversized catalog entries, unused skills. |
| **Unverified Risk** | Runtime or implementation concerns outside config scope | Upstream package compromises, malicious server code implementation, dynamic prompt injection through tool outputs. |
