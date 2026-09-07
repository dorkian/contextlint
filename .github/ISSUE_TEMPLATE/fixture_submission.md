---
name: Anonymized fixture submission
about: Contribute a sanitized real-world configuration to help calibrate contextlint
title: "[Fixture] <Assistant / Use-case name>"
labels: ["fixtures", "community"]
---

## Community Fixture Contribution

Thank you for helping us calibrate `contextlint` and expand our out-of-sample test corpus!

### 1. Assistant Platform
<!-- Select one: Claude Code, Cursor, Codex / AGENTS.md, GitHub Copilot, or Multi-assistant -->

### 2. Configuration Setup Description
<!-- Briefly describe the structure: e.g. 15 skills with nested references, 3 remote MCP servers, monorepo with multiple CLAUDE.md files -->

### 3. Sanitized Snippet or Directory Structure
<!--
CRITICAL: Ensure all API keys, private domains, internal hostnames, and proprietary project names are thoroughly sanitized or replaced with placeholders (e.g. `example.com`, `TEST_KEY_REDACTED`).
-->

```markdown
<!-- Paste sanitized file tree or configuration contents here -->
```

### 4. What should contextlint detect?
<!-- What should the audit report for this setup? (e.g. duplicated rule, oversized catalog entry, unauthenticated server) -->

### 5. Permission
- [ ] I confirm that this configuration snippet contains no proprietary secrets, personal data, or private internal credentials, and I grant permission for it to be included in contextlint's open-source benchmark and test suite under the MIT license.
