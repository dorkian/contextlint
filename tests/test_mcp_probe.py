"""describe()'s redaction, and --mcp-probe-server / --no-network filtering.

describe() is not just documentation — its output is what the interactive
confirmation prompt shows a user *before* any server is started, and it also
ends up verbatim in report.meta['probed_commands'] (so it can land in a saved
JSON/HTML report). A credential-shaped argv value reaching that string would
make this file the second place a secret the security check already flags
leaks in plaintext.
"""

from __future__ import annotations

from contextlint.audit import _probe_servers
from contextlint.mcp_probe import describe
from contextlint.models import Asset


def test_describe_stdio_is_unredacted_for_ordinary_args():
    assert describe({"command": "npx", "args": ["-y", "@example/mcp-server"]}) == (
        "npx -y @example/mcp-server"
    )


def test_describe_redacts_a_flag_value_credential():
    # the exact shape from benchmarks/fixtures/bloated/.mcp.json's "cookie-auth" entry
    out = describe({
        "command": "uvx",
        "args": ["some-webapi-mcp@1.0.0", "--secure-psid",
                 "g.a000FIXTUREx7QsPmNb3vKdW9RtYuIoPaSdFgHjKlZxCvBnM1234567890abcdefgh"],
    })
    assert out == "uvx some-webapi-mcp@1.0.0 --secure-psid [redacted]"
    assert "FIXTURE" not in out


def test_describe_redacts_a_bare_high_entropy_blob_even_without_a_flag():
    blob = "sk-ant-api03-EXAMPLEFIXTUREKEY1234567890abcdefGHIJKLMNOP"
    out = describe({"command": "some-cli", "args": ["--config", blob]})
    assert blob not in out
    assert "[redacted]" in out


def test_describe_does_not_redact_a_placeholder_or_env_reference():
    out = describe({"command": "some-cli", "args": ["--token", "${API_TOKEN}"]})
    assert "${API_TOKEN}" in out
    assert "[redacted]" not in out


def test_describe_http_form_is_unaffected_by_redaction():
    assert describe({"url": "https://api.example.com/mcp"}) == "POST https://api.example.com/mcp"


def test_probe_servers_only_filters_to_named_servers(monkeypatch):
    import contextlint.mcp_probe as mcp_probe_mod

    calls: list[str] = []

    def fake_probe(meta, name, timeout):
        calls.append(name)
        return mcp_probe_mod.ProbeResult(name, True, [])

    monkeypatch.setattr(mcp_probe_mod, "probe", fake_probe)

    assets = [
        Asset(assistant="claude_code", kind="mcp_server", name="github", meta={"command": "gh-mcp"}),
        Asset(assistant="claude_code", kind="mcp_server", name="filesystem", meta={"command": "fs-mcp"}),
        Asset(assistant="claude_code", kind="skill", name="not-a-server", meta={}),
    ]
    _probe_servers(assets, counter=None, timeout=1, on_probe=None, only=["github"])

    assert calls == ["github"]


def test_probe_servers_no_network_skips_http_servers_without_starting_them(monkeypatch):
    import contextlint.mcp_probe as mcp_probe_mod

    calls: list[str] = []
    monkeypatch.setattr(
        mcp_probe_mod, "probe",
        lambda meta, name, timeout: calls.append(name) or mcp_probe_mod.ProbeResult(name, True, []),
    )

    assets = [
        Asset(assistant="claude_code", kind="mcp_server", name="local", meta={"command": "local-mcp"}),
        Asset(assistant="claude_code", kind="mcp_server", name="remote",
              meta={"transport": "http", "url": "https://example.com/mcp"}),
    ]
    _probe_servers(assets, counter=None, timeout=1, on_probe=None, no_network=True)

    assert calls == ["local"]
    remote = next(a for a in assets if a.name == "remote")
    assert "no-network" in remote.meta["probe_error"]


def test_mcp_preflight_shows_servers_without_starting_any(fixture_path, monkeypatch):
    """The confirmation prompt's preview must be buildable from static config
    alone — if it ever imports subprocess or urllib to build itself, a user
    could no longer trust that seeing the preview hasn't already started
    something."""
    import sys

    from contextlint.cli import _mcp_preflight, build_parser

    started = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: started.append(a) or (_ for _ in ()).throw(
        AssertionError("preflight must not start a subprocess")))

    parser = build_parser()
    args = parser.parse_args(["audit", str(fixture_path), "--no-global", "--mcp-probe"])
    lines = _mcp_preflight(args)

    assert not started
    assert any("cookie-auth" in line for line in lines)
    assert not any("FIXTURE" in line for line in lines), "a credential leaked into the preview"


def test_mcp_preflight_respects_probe_server_and_no_network_filters(fixture_path):
    from contextlint.cli import _mcp_preflight, build_parser

    parser = build_parser()
    args = parser.parse_args([
        "audit", str(fixture_path), "--no-global", "--mcp-probe",
        "--mcp-probe-server", "filesystem",
    ])
    lines = _mcp_preflight(args)
    assert len(lines) == 1
    assert lines[0].startswith("  filesystem:")

    args = parser.parse_args([
        "audit", str(fixture_path), "--no-global", "--mcp-probe", "--no-network",
    ])
    lines = _mcp_preflight(args)
    skipped = [l for l in lines if "SKIPPED" in l]
    assert skipped, "an http-transport server should be listed as skipped, not silently dropped"
