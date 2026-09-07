# Security Policy

## Privacy and data handling

The default path reads local files, makes no network connection, and writes nothing. Session
transcripts are parsed for tool-invocation names and timestamps only — never prompt or response
text. Asset content never appears in the JSON or HTML output; only names, paths and counts do.

Two modes are exceptions, both opt-in and both announced at the point of use:

- `--mcp-probe` starts your configured MCP servers to read their real tool schemas. It prints
  the exact commands it will run and asks for interactive confirmation on a TTY.
- `--tokenizer anthropic` sends configuration text to the Anthropic API for exact counting.

For complete details on data sources inspected, execution boundaries, and storage policies,
see **[docs/privacy-and-threat-model.md](docs/privacy-and-threat-model.md)**.

## Security findings scope and non-guarantee

Contextlint identifies known high-risk configuration patterns across coding assistant setups
and MCP configurations.

> **Non-Guarantee**: Contextlint is not a penetration test, does not verify server implementation
> safety, and cannot guarantee that an MCP server, tool description, or agent workflow is safe.
> It reports matched configuration patterns and indicators so you can audit them quickly.

Findings are separated by certainty:

1. **Deterministic facts**: Clear configuration flaws, such as unauthenticated remote endpoints,
   plaintext HTTP transport, credentials passed in CLI argument arrays, or filesystem access rooted at `/`.
2. **Heuristic detections**: Patterns requiring evaluation, such as instruction-shaped tool descriptions,
   obfuscated Unicode-tag characters, or zero-width character sequences.
3. **Unverified runtime risks**: Vulnerabilities in third-party server code, runtime prompt injection
   from tool outputs, or compromised package dependencies cannot be verified by static configuration checks.

## Reporting a vulnerability in contextlint itself

If you discover a security issue in `contextlint` itself, please report it responsibly.
Open a GitHub issue requesting a private security disclosure channel, or contact the maintainers
directly. Vulnerabilities will be addressed and patched promptly.
