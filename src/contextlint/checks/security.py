"""Security checks over agent configuration.

Framing, because it matters: these are heuristics over configuration files, not
proof of a vulnerability and not a substitute for auditing the servers you run.
Every finding names the specific pattern it matched and why that pattern is worth
a look, so you can dismiss it in ten seconds when it is wrong.

Risk classes covered map to the MCP threat model that emerged through 2026: tool
poisoning via instruction text in tool descriptions, unauthenticated remote
servers, unpinned supply chains, command-injection surface in stdio launches,
over-broad filesystem scope, and credentials sitting in plaintext config.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..models import CRITICAL, HIGH, INFO, LOW, MEDIUM, Finding

# Credentials that identify themselves by prefix.
SECRET_PREFIXES = (
    ("sk-ant-", "Anthropic API key"),
    ("sk-proj-", "OpenAI project key"),
    ("sk-", "OpenAI-style API key"),
    ("ghp_", "GitHub personal access token"),
    ("gho_", "GitHub OAuth token"),
    ("github_pat_", "GitHub fine-grained PAT"),
    ("xoxb-", "Slack bot token"),
    ("xoxp-", "Slack user token"),
    ("AKIA", "AWS access key id"),
    ("AIza", "Google API key"),
    ("glpat-", "GitLab PAT"),
    ("dop_v1_", "DigitalOcean token"),
    ("hf_", "HuggingFace token"),
    ("tvly-", "Tavily API key"),
)

SECRET_KEY_RE = re.compile(r"(api[-_]?key|access[-_]?key|token|secret|password|passwd|credential|authorization|x-api-key|\bpat\b|cookie|psid|session)", re.I)

# Credentials passed as command-line arguments rather than environment variables.
# Config files get committed and screenshotted; argv is no safer than env, and it
# additionally leaks to anyone who can run `ps`.
ARG_FLAG_RE = re.compile(r"^--?([A-Za-z0-9_-]*(?:key|token|secret|password|cookie|psid|session|auth|credential)[A-Za-z0-9_-]*)$", re.I)
AUTH_SCHEME_RE = re.compile(r"^\s*(Bearer|Token|Basic|ApiKey)\s+", re.I)
PLACEHOLDER_RE = re.compile(r"^\s*(\$\{?[A-Z_]+\}?|<[^>]+>|\{\{.*\}\}|xxx+|your[-_ ]|changeme|redacted)", re.I)
SHELL_META_RE = re.compile(r"[;&|`$><]|\$\(|\$\{")

# Instruction-shaped text has no business in a description whose only job is to
# help a model choose. In an MCP tool description it is the textbook tool-poisoning
# delivery vector.
POISON_PATTERNS = [
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", "instruction override"),
    (r"disregard\s+(all\s+)?(previous|prior|the\s+above)", "instruction override"),
    (r"do\s+not\s+(tell|inform|mention|reveal)\s+(the\s+)?user", "user concealment"),
    (r"without\s+(telling|informing|asking)\s+the\s+user", "user concealment"),
    (r"\bbefore\s+(using|calling)\s+any\s+other\s+tool\b", "tool-order hijack"),
    (r"<IMPORTANT>|<SYSTEM>|\[\[SYSTEM\]\]", "fake system block"),
    (r"\bread\s+.{0,30}(~/\.ssh|id_rsa|\.env|credentials)", "credential exfiltration"),
    (r"\bsend\s+.{0,40}\bto\s+https?://", "outbound exfiltration"),
]

# Characters that render as nothing. Their only purpose in a config file is to
# hide text from the human reviewing it while the model still reads it.
INVISIBLE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]|[\U000e0000-\U000e007f]"
)

FS_SCOPE_ROOTS = {"/", "~", "$HOME", "/Users", "/home", "C:\\", "/etc", "/var"}

REFS = [
    "OWASP: MCP Top 10 risk classes",
    "NSA/CISA guidance on AI agent tool integration (June 2026)",
]


class SecurityCheck:
    id = "security"
    title = "MCP and configuration security"

    def run(self, ctx) -> list[Finding]:
        out: list[Finding] = []
        for s in ctx.of_kind("mcp_server"):
            out += self._server(s)
        out += self._poison(ctx)
        out += self._secrets_in_context(ctx)
        out += self._permissions(ctx)
        return out

    # --- per MCP server ------------------------------------------------------
    def _server(self, s) -> list[Finding]:
        out: list[Finding] = []
        m = s.meta
        url = str(m.get("url") or "")
        cmd = str(m.get("command") or "")
        args = [str(a) for a in (m.get("args") or [])]
        env = m.get("env") or {}
        headers = m.get("headers") or {}

        # 1. unauthenticated remote server
        if url:
            has_auth = any(k.lower() in ("authorization", "x-api-key") for k in headers) or any(
                SECRET_KEY_RE.search(k) for k in env
            )
            is_local = re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])", url) is not None
            if not has_auth and not is_local:
                out.append(
                    Finding(
                        check=self.id, severity=HIGH,
                        title=f"MCP server '{s.name}' connects to a remote URL with no configured auth",
                        detail=(
                            f"{url} — no Authorization/X-API-Key header and no credential in env. "
                            "Either the endpoint is genuinely unauthenticated, or auth is happening "
                            "somewhere this config does not show. The first case means anyone who can "
                            "reach it can drive your tools."
                        ),
                        remediation="Confirm the server requires auth. Prefer OAuth or a bearer token "
                                    "supplied from the environment, never inline.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )
            if url.startswith("http://") and not is_local:
                out.append(
                    Finding(
                        check=self.id, severity=HIGH,
                        title=f"MCP server '{s.name}' uses plaintext HTTP to a non-local host",
                        detail=f"{url} — tool arguments, results and any bearer token travel unencrypted.",
                        remediation="Switch the endpoint to https.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )

        # 2. plaintext credentials in config
        for k, v in {**env, **headers}.items():
            v = str(v)
            label = _secret_label(k, v)
            if label:
                out.append(
                    Finding(
                        check=self.id, severity=CRITICAL,
                        title=f"Plaintext credential in MCP config: {k} on server '{s.name}'",
                        detail=(
                            f"Looks like a {label}. It sits in {m.get('config_file')}, which is a file "
                            "that routinely gets committed, synced and shared in screenshots."
                        ),
                        remediation=f"Replace the value with ${{{k}}} and export the real one from your "
                                    "shell or a secret manager. Then rotate it — assume it is burned.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )

        # 3. credentials passed as command-line arguments
        reported_args: set[int] = set()
        for i, arg in enumerate(args):
            flag = ARG_FLAG_RE.match(arg)
            value = args[i + 1] if flag and i + 1 < len(args) else ""
            if flag and value and not value.startswith("-") and _secret_label(flag.group(1), value):
                reported_args.add(i + 1)
                out.append(
                    Finding(
                        check=self.id, severity=CRITICAL,
                        title=f"Credential passed as a command-line argument to MCP server '{s.name}': {arg}",
                        detail=(
                            f"`{arg} {value[:6]}…` in {m.get('config_file')}. Arguments are worse than "
                            "environment variables, not better: the config file still gets committed "
                            "and screenshotted, and the value is additionally visible to anyone who "
                            "can run `ps` on this machine. Session cookies are the common case and "
                            "are as good as a password until they expire."
                        ),
                        remediation="Move the value into the server's `env` block referencing a shell "
                                    "variable, or into a credential helper, then rotate it.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )
            elif not flag and i not in reported_args and _looks_like_secret_blob(arg):
                out.append(
                    Finding(
                        check=self.id, severity=HIGH,
                        title=f"High-entropy value in MCP server '{s.name}' arguments",
                        detail=f"A {len(arg)}-character opaque token sits in argv in "
                               f"{m.get('config_file')}. If it is a credential, treat it as exposed.",
                        remediation="Confirm what it is. If it authenticates anything, move it out of "
                                    "the config file and rotate it.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )

        # 4. unpinned remote code execution
        if cmd in ("npx", "npm", "pnpx", "bunx", "uvx", "pipx"):
            spec = next((a for a in args if not a.startswith("-")), "")
            pinned = bool(re.search(r"@\d|==|@[0-9a-f]{7,}", spec))
            if not pinned or "@latest" in spec:
                out.append(
                    Finding(
                        check=self.id, severity=MEDIUM,
                        title=f"MCP server '{s.name}' fetches unpinned code at every launch",
                        detail=(
                            f"`{cmd} {' '.join(args)}` resolves the newest published version each time "
                            "it runs. Whoever can publish that package can run code on this machine on "
                            "your next session, with no review step in between."
                        ),
                        remediation=f"Pin an exact version, e.g. `{spec}@1.2.3`, and update deliberately.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )

        # 5. shell injection surface
        if cmd in ("sh", "bash", "zsh", "cmd", "powershell") and any(a in ("-c", "/c", "-Command") for a in args):
            out.append(
                Finding(
                    check=self.id, severity=HIGH,
                    title=f"MCP server '{s.name}' launches through a shell",
                    detail=f"`{cmd} {' '.join(args)}` — any value interpolated into that string is "
                           "executed by the shell, not passed as an argument.",
                    remediation="Invoke the server binary directly with a plain argv list.",
                    asset_id=s.id, path=s.path, refs=REFS,
                )
            )
        elif any(SHELL_META_RE.search(a) for a in args):
            out.append(
                Finding(
                    check=self.id, severity=MEDIUM,
                    title=f"MCP server '{s.name}' has shell metacharacters in its arguments",
                    detail=f"args: {args}",
                    remediation="Confirm these are literal. If a launcher expands them, they are an "
                                "injection point.",
                    asset_id=s.id, path=s.path, refs=REFS,
                )
            )

        # 6. filesystem scope creep
        if "filesystem" in s.name.lower() or any("filesystem" in a.lower() for a in args):
            broad = [a for a in args if a in FS_SCOPE_ROOTS or a.rstrip("/") in ("", str(Path.home()))]
            if broad:
                out.append(
                    Finding(
                        check=self.id, severity=HIGH,
                        title=f"Filesystem MCP server '{s.name}' is scoped to {', '.join(broad)}",
                        detail=(
                            "A filesystem server rooted at your home directory or / can read anything "
                            "you can: SSH keys, browser profiles, .env files, other clients' tokens. "
                            "Combined with any tool that can make a network call, that is an "
                            "exfiltration path that needs no exploit."
                        ),
                        remediation="Scope the server to the specific project directories it needs.",
                        asset_id=s.id, path=s.path, refs=REFS,
                    )
                )
        return out

    # --- tool poisoning ------------------------------------------------------
    def _poison(self, ctx) -> list[Finding]:
        out: list[Finding] = []
        for a in ctx.assets:
            text = a.always_on_text or ""
            if a.kind == "mcp_server":
                text += json.dumps(a.meta.get("tool_descriptions") or [])

            hidden = INVISIBLE_RE.findall(text)
            if hidden:
                out.append(
                    Finding(
                        check=self.id, severity=CRITICAL,
                        title=f"Invisible characters in always-on text of '{a.name}'",
                        detail=(
                            f"{len(hidden)} zero-width, bidi-override or Unicode-tag character(s) in "
                            "content that is injected into the system prompt. These render as nothing "
                            "to you and as text to the model — the standard way to hide an instruction "
                            "from the person reviewing the file."
                        ),
                        remediation="Open the file with invisible characters shown and delete them. If "
                                    "you did not put them there, treat the source as compromised.",
                        asset_id=a.id, path=a.path, refs=REFS,
                    )
                )

            for pattern, label in POISON_PATTERNS:
                m = re.search(pattern, text, re.I)
                if not m:
                    continue
                is_tool = a.kind in ("mcp_server", "mcp_tool")
                out.append(
                    Finding(
                        check=self.id,
                        severity=CRITICAL if is_tool else MEDIUM,
                        title=f"Instruction-shaped text ({label}) in '{a.name}'",
                        detail=(
                            f"Matched {m.group(0)!r}. "
                            + (
                                "In an MCP tool description this is the tool-poisoning pattern directly: "
                                "the server author is writing instructions into text your assistant reads "
                                "as trusted context."
                                if is_tool
                                else "In a skill description this is usually just emphatic writing. Worth "
                                "a glance to confirm you wrote it, and worth removing either way — "
                                "descriptions should say when to load, not issue orders."
                            )
                        ),
                        remediation="Read the surrounding text. Remove it if you did not write it.",
                        asset_id=a.id, path=a.path, refs=REFS,
                    )
                )
        return out

    # --- credentials pasted into context ------------------------------------
    def _secrets_in_context(self, ctx) -> list[Finding]:
        out: list[Finding] = []
        for a in ctx.assets:
            if a.kind == "mcp_server":
                continue
            blob = f"{a.always_on_text}\n{a.on_demand_text}"
            for prefix, label in SECRET_PREFIXES:
                pattern = r"(?<![A-Za-z0-9_./-])" + re.escape(prefix) + r"[A-Za-z0-9_\-]{12,}"
                for m in re.finditer(pattern, blob):
                    tok = m.group(0)
                    if not _looks_like_key(tok[len(prefix):]):
                        continue
                    out.append(
                        Finding(
                            check=self.id, severity=CRITICAL,
                            title=f"Possible {label} inside '{a.name}'",
                            detail=(
                                f"Matched `{tok[:len(prefix) + 4]}…` in {a.path}. Content in this file "
                                "is injected into prompts, so the credential travels to the model "
                                "provider on every request that loads it."
                            ),
                            remediation="Remove it, rotate the credential, and reference an environment "
                                        "variable by name instead.",
                            asset_id=a.id, path=a.path, refs=REFS,
                        )
                    )
                    break
        return out

    # --- permissions and hooks ----------------------------------------------
    def _permissions(self, ctx) -> list[Finding]:
        out: list[Finding] = []
        for root in ctx.workspace.roots():
            for rel in (".claude/settings.json", ".claude/settings.local.json"):
                p = root / rel
                if not p.is_file():
                    continue
                try:
                    data = json.loads(p.read_text(encoding="utf-8", errors="replace") or "{}")
                except (OSError, json.JSONDecodeError):
                    continue

                allow = ((data.get("permissions") or {}).get("allow")) or []
                wild = [
                    r for r in allow
                    if isinstance(r, str)
                    and (r in ("*", "Bash", "Bash(*)", "Bash(*:*)") or r.endswith("(*)") and r.startswith("Bash"))
                ]
                if wild:
                    out.append(
                        Finding(
                            check=self.id, severity=HIGH,
                            title=f"Blanket command permission in {rel}",
                            detail=f"Allow rules {wild} pre-approve arbitrary commands, so the "
                                   "confirmation step that would catch a prompt-injected command never "
                                   "runs.",
                            remediation="Replace with specific prefixes, e.g. `Bash(git status)`, "
                                        "`Bash(npm test:*)`.",
                            path=p, refs=REFS,
                        )
                    )

                hooks = data.get("hooks") or {}
                if hooks:
                    events = ", ".join(sorted(hooks)) if isinstance(hooks, dict) else "configured"
                    out.append(
                        Finding(
                            check=self.id, severity=INFO,
                            title=f"Hooks configured in {rel} ({events})",
                            detail="Hooks run shell commands automatically around tool calls, outside "
                                   "the permission prompt. Not a problem — just the highest-trust code "
                                   "in your setup, and worth re-reading when you did not write it.",
                            remediation="Confirm every hook command is one you authored.",
                            path=p, refs=REFS,
                        )
                    )

                if isinstance(data.get("env"), dict):
                    for k, v in data["env"].items():
                        if _secret_label(k, str(v)):
                            out.append(
                                Finding(
                                    check=self.id, severity=CRITICAL,
                                    title=f"Plaintext credential in {rel}: {k}",
                                    detail="Settings files are routinely committed and synced.",
                                    remediation="Move it to your shell environment and rotate it.",
                                    path=p, refs=REFS,
                                )
                            )
        return out


def _looks_like_secret_blob(value: str) -> bool:
    """A long, dense, non-word string in argv is a credential until proven otherwise."""
    if len(value) < 40 or value.startswith(("-", "/", "~", "http")) or " " in value:
        return False
    alnum = sum(c.isalnum() for c in value)
    if alnum / len(value) < 0.8:
        return False
    return (
        any(c.isdigit() for c in value)
        and any(c.isupper() for c in value)
        and any(c.islower() for c in value)
    )


def _looks_like_key(body: str) -> bool:
    """Reject prose that happens to start with a short prefix.

    ``sk-`` matches the middle of ``scheduled-task-tool-approval`` and ``hf_`` matches
    plenty of snake_case. A real key is dense: it mixes digits with letters, or it is
    long and not made of dictionary-shaped words separated by punctuation.
    """
    if not body:
        return False
    has_digit = any(c.isdigit() for c in body)
    has_alpha = any(c.isalpha() for c in body)
    words = [w for w in re.split(r"[-_]", body) if w]
    wordy = len(words) >= 3 and all(w.isalpha() for w in words)
    if wordy:
        return False
    if has_digit and has_alpha:
        return True
    return len(body) >= 24 and any(c.isupper() for c in body) and any(c.islower() for c in body)


def _secret_label(key: str, value: str) -> str | None:
    """Classify a config value as a credential, or return None.

    Strips the auth scheme first: `Authorization: Bearer sk-ant-...` is the single
    most common way a real key ends up committed, and matching only on raw prefixes
    walks straight past it.
    """
    if not value:
        return None
    value = AUTH_SCHEME_RE.sub("", value).strip()
    if not value or PLACEHOLDER_RE.match(value):
        return None
    for prefix, label in SECRET_PREFIXES:
        if value.startswith(prefix) and _looks_like_key(value[len(prefix):]):
            return label
    if SECRET_KEY_RE.search(key) and len(value) >= 16 and not value.startswith("$"):
        return "credential"
    return None
