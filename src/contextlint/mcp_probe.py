"""Measure MCP tool-schema cost exactly, by asking the server.

Static config tells you a server exists. It cannot tell you the server publishes
41 tools whose JSON schemas cost 12,000 tokens on every single turn — that number
only exists on the wire. So contextlint offers both, and is explicit about which
one you are reading:

* default — servers are counted, their schema cost is left ``None`` and the
  report says "unmeasured" rather than inventing a per-tool average.
* ``--mcp-probe`` — opt-in. Starts each stdio server as a subprocess, or POSTs to
  each HTTP server, runs the MCP handshake, and prices the real ``tools/list``.

Probing runs third-party code and opens network connections. That is why it is a
flag and not a default, and why the CLI prints exactly what it is about to run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "contextlint", "version": "0.1.0"}
DEFAULT_TIMEOUT = 20.0


@dataclass
class ProbeResult:
    server: str
    ok: bool
    tools: list[dict[str, Any]]
    error: str = ""
    transport: str = ""

    @property
    def schema_text(self) -> str:
        """The text an assistant actually injects for these tools.

        Serialising name + description + inputSchema as compact JSON is what the
        tool-definition block costs; formatting differs slightly per client, and
        the README says so rather than pretending this is exact to the token.
        """
        return "\n".join(
            json.dumps(
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema") or t.get("input_schema") or {},
                },
                separators=(",", ":"),
            )
            for t in self.tools
        )


def probe(asset_meta: dict[str, Any], name: str, timeout: float = DEFAULT_TIMEOUT) -> ProbeResult:
    transport = asset_meta.get("transport") or "unknown"
    try:
        if transport == "stdio" or asset_meta.get("command"):
            return _probe_stdio(name, asset_meta, timeout)
        if asset_meta.get("url"):
            return _probe_http(name, asset_meta, timeout)
    except Exception as exc:  # a failed probe must never abort the audit
        return ProbeResult(name, False, [], f"{type(exc).__name__}: {exc}", transport)
    return ProbeResult(name, False, [], "no command or url in config", transport)


def describe(asset_meta: dict[str, Any]) -> str:
    """What probing this server will actually do, for the pre-flight warning."""
    if asset_meta.get("command"):
        return " ".join([str(asset_meta["command"]), *[str(a) for a in asset_meta.get("args") or []]])
    return f"POST {asset_meta.get('url')}"


# --- stdio -------------------------------------------------------------------

def _probe_stdio(name: str, cfg: dict[str, Any], timeout: float) -> ProbeResult:
    cmd = [str(cfg["command"]), *[str(a) for a in cfg.get("args") or []]]
    if not shutil.which(cmd[0]):
        return ProbeResult(name, False, [], f"command not found: {cmd[0]}", "stdio")

    env = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}}
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=env, text=True, bufsize=1,
    )
    try:
        payload = (
            _rpc(1, "initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            })
            + _rpc(None, "notifications/initialized", {})
            + _rpc(2, "tools/list", {})
        )
        out, _ = proc.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return ProbeResult(name, False, [], f"timed out after {timeout:g}s", "stdio")
    finally:
        if proc.poll() is None:
            proc.kill()

    tools = _tools_from_stream(out)
    if tools is None:
        return ProbeResult(name, False, [], "no tools/list response", "stdio")
    return ProbeResult(name, True, tools, "", "stdio")


# --- http --------------------------------------------------------------------

def _probe_http(name: str, cfg: dict[str, Any], timeout: float) -> ProbeResult:
    url = str(cfg["url"])
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        **{str(k): str(v) for k, v in (cfg.get("headers") or {}).items()},
    }

    def post(body: dict) -> str:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — user-configured URL
            sid = r.headers.get("Mcp-Session-Id")
            if sid:
                headers["Mcp-Session-Id"] = sid
            return r.read().decode("utf-8", "replace")

    try:
        post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                         "clientInfo": CLIENT_INFO}})
        raw = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    except urllib.error.HTTPError as exc:
        return ProbeResult(name, False, [], f"HTTP {exc.code}", "http")
    except urllib.error.URLError as exc:
        return ProbeResult(name, False, [], f"unreachable: {exc.reason}", "http")

    tools = _tools_from_stream(raw)
    if tools is None:
        return ProbeResult(name, False, [], "no tools/list response", "http")
    return ProbeResult(name, True, tools, "", "http")


# --- shared ------------------------------------------------------------------

def _rpc(msg_id: int | None, method: str, params: dict) -> str:
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
    if msg_id is not None:
        body["id"] = msg_id
    return json.dumps(body) + "\n"


def _tools_from_stream(raw: str) -> list[dict[str, Any]] | None:
    """Pull the tools array out of newline-JSON or SSE, whichever the server spoke."""
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        tools = (msg.get("result") or {}).get("tools")
        if isinstance(tools, list):
            return tools
    return None
