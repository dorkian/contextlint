from pathlib import Path

from contextlint.discovery import (
    Workspace,
    has_config,
    parse_frontmatter,
    split_frontmatter,
)


def test_split_frontmatter_basic():
    fm, body = split_frontmatter("---\nname: x\ndescription: y\n---\nbody here\n")
    assert fm == {"name": "x", "description": "y"}
    assert body.strip() == "body here"


def test_no_frontmatter_returns_whole_text():
    fm, body = split_frontmatter("You are running a pipeline.\nStep 1.")
    assert fm == {}
    assert body.startswith("You are running")


def test_unterminated_frontmatter_is_not_frontmatter():
    fm, body = split_frontmatter("---\nname: x\nno terminator")
    assert fm == {}
    assert "no terminator" in body


def test_scalars_and_lists():
    fm = parse_frontmatter(
        'name: "quoted"\nflag: true\nother: false\nnil: null\n'
        'inline: [a, b, c]\nblock:\n  - one\n  - two\n'
    )
    assert fm["name"] == "quoted"
    assert fm["flag"] is True and fm["other"] is False
    assert fm["nil"] is None
    assert fm["inline"] == ["a", "b", "c"]
    assert fm["block"] == ["one", "two"]


def test_folded_multiline_value_is_joined():
    fm = parse_frontmatter("description: first part\n  second part\n")
    assert fm["description"] == "first part second part"


def test_directory_with_config_wins_over_git_root(fixture_path):
    ws = Workspace.resolve(str(fixture_path), include_global=False)
    assert ws.project == fixture_path, "a directory carrying agent config is the project"


def test_has_config_detects_each_marker(tmp_path: Path):
    assert not has_config(tmp_path)
    (tmp_path / "AGENTS.md").write_text("x")
    assert has_config(tmp_path)


def test_scope_of(fixture_path):
    ws = Workspace.resolve(str(fixture_path), include_global=False)
    assert ws.scope_of(fixture_path / "CLAUDE.md") == "project"
    assert ws.scope_of(Path("/etc/hosts")) == "global"
