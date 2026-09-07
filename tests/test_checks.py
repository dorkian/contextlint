"""Every vulnerability planted in the fixture must be found.

This file is the security claim. If a check regresses, the claim fails here rather
than in someone's repository.
"""

import pytest

from contextlint.models import CRITICAL, HIGH


def titles(report, check=None):
    return [f.title for f in report.findings if check is None or f.check == check]


def find(report, needle):
    return [f for f in report.findings if needle.lower() in f.title.lower()]


@pytest.mark.parametrize(
    "needle,severity",
    [
        ("Invisible characters", CRITICAL),
        ("Plaintext credential in MCP config", CRITICAL),
        ("no configured auth", HIGH),
        ("plaintext HTTP", HIGH),
        ("launches through a shell", HIGH),
        ("scoped to /", HIGH),
        ("Blanket command permission", HIGH),
    ],
)
def test_planted_vulnerability_is_caught(bloated_report, needle, severity):
    hits = find(bloated_report, needle)
    assert hits, f"missed: {needle}\nsaw: {titles(bloated_report, 'security')}"
    assert hits[0].severity == severity


def test_unpinned_supply_chain_is_flagged(bloated_report):
    assert find(bloated_report, "unpinned code")


@pytest.mark.parametrize(
    "label",
    ["instruction override", "user concealment", "tool-order hijack", "credential exfiltration"],
)
def test_each_poisoning_pattern_is_caught(bloated_report, label):
    assert find(bloated_report, label)


def test_byte_identical_duplicate_is_found(bloated_report):
    hits = find(bloated_report, "byte-identical")
    assert hits and hits[0].fixable and hits[0].fix_hint["action"] == "delete"


def test_name_shadowing_is_found(bloated_report):
    assert find(bloated_report, "defined 3 times")


def test_empty_skill_is_found(bloated_report):
    assert find(bloated_report, "effectively empty")


def test_pinned_server_is_not_flagged_as_unpinned(bloated_report):
    """The filesystem server pins @1.0.0 — flagging it would be a false positive."""
    assert not [f for f in find(bloated_report, "unpinned code") if "filesystem" in f.title]


def test_prose_starting_with_a_key_prefix_is_not_a_secret(tmp_path):
    """`sk-` appears inside ordinary hyphenated words; matching it caused a false CRITICAL."""
    from contextlint.audit import run_audit

    d = tmp_path / ".claude" / "skills" / "notes"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: notes\ndescription: Notes.\n---\n"
        "See reference_scheduled_task_tool_approval_per_task and risk-taking-tolerance-levels.\n"
    )
    report = run_audit(str(tmp_path), include_global=False, use_usage=False)
    assert not [f for f in report.findings if "API key" in f.title]


def test_env_var_placeholder_is_not_a_secret(tmp_path):
    from contextlint.audit import run_audit

    (tmp_path / ".mcp.json").write_text(
        '{"mcpServers":{"s":{"type":"http","url":"https://x/mcp",'
        '"headers":{"Authorization":"Bearer ${MY_TOKEN}"}}}}'
    )
    report = run_audit(str(tmp_path), include_global=False, use_usage=False)
    assert not [f for f in report.findings if "Plaintext credential" in f.title]


def test_localhost_without_auth_is_not_flagged(tmp_path):
    from contextlint.audit import run_audit

    (tmp_path / ".mcp.json").write_text(
        '{"mcpServers":{"local":{"type":"http","url":"http://localhost:3000/mcp"}}}'
    )
    report = run_audit(str(tmp_path), include_global=False, use_usage=False)
    assert not [f for f in report.findings if "no configured auth" in f.title]
    assert not [f for f in report.findings if "plaintext HTTP" in f.title]


def test_check_selection(fixture_path):
    from contextlint.audit import run_audit

    only = run_audit(str(fixture_path), include_global=False, use_usage=False,
                     only_checks=["security"])
    assert {f.check for f in only.findings} == {"security"}

    skipped = run_audit(str(fixture_path), include_global=False, use_usage=False,
                        skip_checks=["security"])
    assert "security" not in {f.check for f in skipped.findings}
