# contextlint — v1 specification

The contract this version implements. Written before the code, kept in sync with it.

## Problem

An AI coding assistant loads skills, instruction files, memory and MCP tool schemas into the
system prompt before the user's first message. That cost is per-request, invisible, spread
across four config formats and two directory trees, and nothing reports the total. Beyond
money, the bloat degrades tool-selection accuracy.

Existing tools address one slice each: token accounting for Claude Code only, or MCP security
scanning with no cost model. None correlate configuration against real usage, none cross
assistant boundaries, and none publish a reproduction path for their savings claims.

## Scope

**In:** static parsing of Claude Code, Codex/AGENTS.md, Cursor and Copilot configuration; token
pricing that distinguishes always-on from on-demand cost; correlation against local session
transcripts; MCP configuration security checks; optional live measurement of MCP tool schemas;
terminal, JSON and self-contained HTML output; a conservative auto-fix with backups; a
reproducible benchmark harness.

**Out:** hosted services or dashboards; uploading configuration anywhere; runtime interception
of agent traffic; auditing the security of MCP server *implementations* (this reads config, not
source); rewriting skill content.

## Requirements

### R1 — Loading modes
Each asset is classified `always`, `on_demand`, `conditional` or `deferred`. Always-on cost and
on-demand cost are priced separately and never summed into one headline. A skill's always-on
cost is its catalog entry, not its body. *Verified by `test_adapters.py`.*

### R2 — Adapters
One module per assistant behind a `detect`/`collect` protocol. Adding an assistant touches one
file and one registry entry. Malformed input degrades to a partial result, never a crash.
*Verified by `test_adapters.py`, `test_discovery.py`.*

### R3 — Token counting
Default is an offline, zero-dependency heuristic whose parameters are fitted against a real
tokenizer and whose error is published. `tiktoken` and Anthropic `count_tokens` are opt-in exact
backends. An exact backend that is unavailable falls back with a warning, except under
`strict`, where it raises — so a benchmark can never silently report an estimate as a
measurement. *Verified by `test_tokens.py`; error measured by `benchmarks/calibrate.py`.*

### R4 — Usage correlation
Local session transcripts are parsed for tool-invocation names and timestamps only. Assets
installed but never invoked are reported, with an explicit statement that this is a prompt to
review rather than a verdict. Absence of transcripts disables the check with a stated reason
rather than silently producing a less accurate report. *Verified by `test_checks.py`.*

### R5 — Security
Checks cover: unauthenticated remote MCP servers, plaintext HTTP, credentials in configuration
(including behind an auth scheme prefix), unpinned remote-code supply chains, shell-launched
servers, filesystem scope creep, instruction-shaped text and invisible characters in always-on
content, and blanket permission rules. Findings state the matched pattern and are framed as
signals. False-positive resistance is itself tested. *Verified by `test_checks.py`; detection
rate by `benchmarks/run.py`.*

### R6 — Savings arithmetic
Recoverable tokens are the union of the *assets* findings put at stake, priced once each — not
the sum of per-finding claims. Certain savings (behaviour-preserving) and candidate savings
(judgement calls) are reported as two disjoint numbers. *Verified by `test_models.py`.*

### R7 — Write safety
`audit` never writes. `fix` prints a plan and changes nothing without `--apply`; refuses a
dirty git tree without `--allow-dirty`; backs every removal into a timestamped directory with a
generated `restore.sh`. Only byte-identical duplicates and empty assets are auto-fixable.
*Verified by `test_fix.py`, `test_cli.py`.*

### R8 — MCP probing
Off by default. When enabled, prints the exact commands it will run and requires confirmation
on a TTY. A failed probe degrades that server to unmeasured and never aborts the audit.
Unmeasured schema cost is excluded from totals and labelled.

### R9 — Output
Terminal (colour on a TTY), JSON, and a single self-contained HTML file with no external
resource of any kind. Asset *content* never appears in JSON or HTML output — only names, paths
and counts. `--fail-on` gives CI a severity threshold. *Verified by `test_cli.py`,
`test_models.py`.*

### R11 — Health over time
`watch` repeats the audit and reports *drift* against the previous run: token delta, findings
that are new, findings that are gone. Snapshots persist to a JSONL history so `--once` under an
external scheduler compares correctly. Finding fingerprints are number-insensitive, so a changed
count inside a title does not read as one finding resolved and another appearing. Drift is
suppressed, with a stated reason, when the two runs used different measurement modes (probed vs
not, or a different tokenizer). Exit code is 0 for ok/warn and 1 for fail. *Verified by
`test_history.py`, `test_cli.py`.*

### R12 — Portable undo
Backups are addressed through a manifest, not a shell script, so the undo works on Windows.
Backup filenames are derived from absolute source paths and must contain no path separator, no
drive anchor and no character illegal on Windows. `restore` refuses to overwrite a path that
exists again unless forced. *Verified by `test_fix.py`, `test_cli.py`.*

### R10 — Reproducibility
`benchmarks/run.py` regenerates every published number. Detection is measured against a fixture
containing one instance of each defect class. Savings are measured as the difference between
two real audits of a copy that the real `fix` path has been run against. Tokenizer parameters
are fitted on half the corpus and the error is reported on the other half.

## Definition of done

1. `pytest` green on Linux, macOS **and Windows**, covering every requirement marked *Verified* above.
2. `benchmarks/run.py` reports 15/15 detection and exits 0.
3. `contextlint audit` runs on a machine with no network and no API key.
4. All four adapters parse the fixture and produce the expected loading-mode classification.
5. Every number in the README is regenerable by a command printed in the README.
6. The HTML report contains no external URL.
