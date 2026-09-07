# Roadmap

`contextlint` focuses on trust, measurement integrity, and cross-assistant configuration security.

This roadmap follows a **Now / Next / Later** cadence.

---

## Now (v0.1.x)

- [x] **Cross-assistant core**: Claude Code, Codex, Cursor, and GitHub Copilot support.
- [x] **Loading-mode accounting**: Distinguish always-on catalog floor from on-demand body costs.
- [x] **Real session correlation**: Transcripts correlated with always-on asset costs.
- [x] **MCP configuration security**: Plaintext HTTP, credentials in argv/env, shell execution, root filesystem access, and hidden Unicode-tag characters.
- [x] **Reproducible benchmarks**: Published detection and savings verified via `benchmarks/run.py`.
- [x] **Interactive dashboard**: Localhost React/Vite dashboard matching visual report design.
- [x] **Privacy & threat model**: Explicit boundaries, transcript data isolation, and non-guarantee statements.

---

## Next (v0.2.x)

- [ ] **Community fixture corpus**: Collect and integrate sanitized configurations across diverse platforms to stress-test heuristic error and false positives.
- [ ] **Granular `--mcp-probe` targeting**: Allow probing a single named server (e.g. `--mcp-probe <server-name>`).
- [ ] **Finding suppression rules**: Support a `.contextlintignore` file to dismiss intentional configurations with reasons.
- [ ] **Structured CI output formats**: SARIF (Static Analysis Results Interchange Format) output for GitHub Code Scanning and GitLab Security dashboards.
- [ ] **Extended security checks**: Flag excessive tool permissions and wildcard path approvals in assistant configurations.

---

## Later (v1.0+)

- [ ] **Windsurf & Zed adapter support**: Expand adapter coverage to emerging agentic IDEs.
- [ ] **Model context window profiles**: Built-in context window definitions for Claude 3.7 Sonnet, GPT-4o, Gemini 2.5 Pro, and DeepSeek.
- [ ] **Pre-commit integration package**: Ready-to-use pre-commit hooks for team-wide context hygiene enforcement.
- [ ] **Cross-assistant migration helper**: Convert always-on instructions between Cursor `.cursorrules` and Codex `AGENTS.md` safely.
