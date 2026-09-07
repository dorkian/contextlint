# Security

## What contextlint does with your data

The default path reads local files, makes no network connection, and writes nothing. Session
transcripts are parsed for tool-invocation names and timestamps only — never prompt or response
text. Asset content never appears in the JSON or HTML output; only names, paths and counts do.

Two modes are exceptions, both opt-in and both stated at the point of use:

- `--mcp-probe` starts your configured MCP servers to read their real tool schemas. It prints
  the exact commands it will run and asks for confirmation on a TTY.
- `--tokenizer anthropic` sends configuration text to the Anthropic API for exact counting.

## What its security findings mean

They are heuristics over configuration files. They are not proof of a vulnerability, and they
are not a substitute for auditing the servers you actually run. Every finding names the pattern
it matched and why that pattern is worth a look, so a false positive costs you ten seconds.

contextlint reads configuration. It does not analyse MCP server source code, does not attempt
exploitation, and does not send anything to a scanning service.

## Reporting a vulnerability in contextlint itself

Open a GitHub issue. If the report itself is sensitive, say so in the issue without details and
a private channel will be arranged.
