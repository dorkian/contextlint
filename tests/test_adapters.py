from contextlint.models import ALWAYS, CONDITIONAL, ON_DEMAND


def _by_name(report, kind, name):
    return next(a for a in report.assets if a.kind == kind and a.name == name)


def test_all_four_adapters_detect_the_fixture(bloated_report):
    assert set(bloated_report.meta["assistants_detected"]) == {
        "claude_code", "codex", "cursor", "copilot"
    }


def test_skill_body_is_on_demand_not_always_on(bloated_report):
    """The correctness claim the whole project rests on."""
    alpha = _by_name(bloated_report, "skill", "alpha")
    assert alpha.loading == ON_DEMAND
    assert alpha.on_demand_tokens > alpha.always_on_tokens
    assert "Preserve issue and PR references" not in alpha.always_on_text
    assert "summarise a changelog" in alpha.always_on_text


def test_claude_md_is_always_on_in_full(bloated_report):
    claude_md = next(a for a in bloated_report.assets if a.name.endswith("CLAUDE.md"))
    assert claude_md.loading == ALWAYS
    assert "Prefer small diffs" in claude_md.always_on_text
    assert claude_md.on_demand_tokens == 0


def test_cursor_always_apply_versus_globbed(bloated_report):
    always = _by_name(bloated_report, "rule", "always")
    tests = _by_name(bloated_report, "rule", "tests")
    assert always.loading == ALWAYS and always.always_on_tokens > 0
    assert tests.loading == CONDITIONAL and tests.always_on_tokens == 0


def test_copilot_apply_to_makes_it_conditional(bloated_report):
    py = _by_name(bloated_report, "instruction", "python")
    assert py.meta["apply_to"] == "**/*.py"
    assert py.loading == CONDITIONAL


def test_every_mcp_server_in_one_file_is_its_own_asset(bloated_report):
    servers = {a.name for a in bloated_report.assets if a.kind == "mcp_server"}
    assert servers == {"public-notes", "unpinned", "shelled", "filesystem", "leaky", "cookie-auth"}


def test_asset_ids_are_unique(bloated_report):
    ids = [a.id for a in bloated_report.assets]
    assert len(ids) == len(set(ids))


def test_missing_frontmatter_is_recorded_not_crashed(tmp_path):
    from contextlint.adapters.claude_code import ClaudeCodeAdapter
    from contextlint.discovery import Workspace

    d = tmp_path / ".claude" / "skills" / "raw"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("You are running a pipeline with no frontmatter at all.")
    ws = Workspace.resolve(str(tmp_path), include_global=False)
    asset = next(a for a in ClaudeCodeAdapter().collect(ws) if a.kind == "skill")
    assert asset.meta["missing_frontmatter"] is True
    assert asset.name == "raw"
    assert "no frontmatter" in asset.always_on_text


def test_only_the_current_projects_memory_index_is_always_on(tmp_path):
    """~/.claude/projects/ holds a directory per project the user has ever opened.
    Only the current project's MEMORY.md is injected into the current project's
    sessions; the siblings belong to other repos."""
    from contextlint.adapters.claude_code import ClaudeCodeAdapter
    from contextlint.discovery import Workspace

    home = tmp_path / "home"
    project = home / "code" / "myproj"
    project.mkdir(parents=True)
    (project / "CLAUDE.md").write_text("project rules")

    projects = home / ".claude" / "projects"
    slug = str(project).replace("/", "-").replace(".", "-")
    (projects / slug / "memory").mkdir(parents=True)
    (projects / slug / "memory" / "MEMORY.md").write_text("- [a](a.md) mine")
    (projects / "-Users-someone-vault" / "memory").mkdir(parents=True)
    (projects / "-Users-someone-vault" / "memory" / "MEMORY.md").write_text("- [b](b.md) theirs")

    ws = Workspace(project=project, home=home, include_global=True)
    memory_files = {
        str(a.path)
        for a in ClaudeCodeAdapter().collect(ws)
        if a.path and a.path.name == "MEMORY.md"
    }
    assert memory_files == {str(projects / slug / "memory" / "MEMORY.md")}
