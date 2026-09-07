# benchmarks

Every number contextlint publishes is regenerated here. Nothing in the README is a figure
without a command.

```bash
python benchmarks/run.py                                            # detection + savings
uv run --no-project --with tiktoken python benchmarks/calibrate.py  # tokenizer error
uv run --no-project --with tiktoken python benchmarks/tune.py       # refit the heuristic
```

## `fixtures/bloated/`

A workspace configured for all four assistants, containing exactly one instance of each defect
class contextlint claims to detect: a byte-identical duplicate skill, a same-name shadow with
different content, an empty skill, a skill whose description carries hidden instruction text
and a zero-width character, and five MCP servers that are respectively unauthenticated over
plaintext HTTP, unpinned, shell-launched, rooted at `/`, and carrying a plaintext bearer token.

The credential in `.mcp.json` is a syntactically valid but fabricated string. It is not a real
key and never was.

Detection is measured against this fixture. A tool that reports savings but misses defects is
not measuring anything useful, so `run.py` exits non-zero if detection is not 15/15.

## `run.py` — detection and savings

Savings are measured, not estimated: the fixture is copied, the real `fix` code path is run
against the copy, and the copy is audited again. The reported percentage is the difference
between two audits.

Only automatic fixes count toward it. Judgement-call findings — a skill you have not invoked in
90 days — are excluded on purpose. Including them is how a modest, honest number becomes an
implausible one.

## `calibrate.py` — tokenizer error

Compares the offline heuristic against `tiktoken` o200k_base over a corpus of real agent
configuration: markdown skills, JSON tool schemas, YAML frontmatter. Reports aggregate error
(what matters for a total), median, p90 and worst per-file error, broken down by extension.

Calibrating on prose would flatter the result, so the corpus is deliberately the kind of text
contextlint actually counts.

## `tune.py` — refitting

Coordinate descent over the heuristic's seven parameters. Splits the corpus deterministically,
fits on the training half and reports error on the held-out half, then prints a
`HeuristicParams(...)` block to paste into `src/contextlint/tokens.py`.

It does not write to the source tree. A tool whose headline is measurement honesty should make
changing its own measurement an explicit, reviewed act.

## `results/`

Generated JSON, git-ignored. Regenerate rather than trust a checked-in copy.
