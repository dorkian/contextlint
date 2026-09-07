"""The docs/CI guard that catches an unrunnable install line before a reader does.

Covers the two failure modes it has actually had: missing the real thing (the
original `uvx contextlint` bug), and flagging its own negated warning about that
exact bug (discovered while writing the "paste this into your AI assistant"
install prompt, whose warning text necessarily contains the bad command as an
example of what not to run).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_install_claims import CLAIM, EXEMPT, NEGATION_AFTER, NEGATION_BEFORE  # noqa: E402


def _is_claim(line: str) -> bool:
    """Mirrors main()'s per-line logic exactly, so these tests exercise the
    real decision the checker makes rather than a re-implementation of it."""
    m = CLAIM.search(line)
    if not m or any(e in line for e in EXEMPT):
        return False
    same_clause = re.split(r"[.;!?\n]", line[m.end() :], maxsplit=1)[0]
    if NEGATION_BEFORE.search(line[: m.start()]) or NEGATION_AFTER.search(same_clause):
        return False
    return True


def test_a_bare_install_is_a_claim():
    assert _is_claim("pip install contextlint")
    assert _is_claim("uvx contextlint")
    assert _is_claim('uv tool install "contextlint[exact]"')


def test_a_git_install_is_not_a_claim():
    assert not _is_claim("pip install git+https://github.com/dorkian/contextlint")
    assert not _is_claim("uvx --from git+https://github.com/dorkian/contextlint contextlint")


def test_a_negated_warning_is_not_a_claim():
    """The exact sentence from the README's AI-assistant install prompt."""
    assert not _is_claim("do not run a bare `pip install contextlint` — it will 404")
    assert not _is_claim("Do not run `pip install contextlint`, it 404s.")
    assert not _is_claim("never run pip install contextlint directly")


def test_a_forward_outcome_cue_is_not_a_claim():
    """The other real shape of this warning: 'X will 404' instead of 'do not
    run X'. Exact sentence from README.md's "Install via your AI assistant"."""
    assert not _is_claim(
        "so a bare `pip install contextlint` or `uvx contextlint` will 404; that's expected"
    )
    assert not _is_claim("uvx contextlint doesn't work, use --from instead")


def test_negation_before_only_suppresses_when_it_precedes_the_match():
    """A 'do not'-style cue *after* the command must not retroactively excuse
    it — only text earlier in the line establishes that this was a warning."""
    assert _is_claim("pip install contextlint, do not skip this step")


def test_a_distant_outcome_cue_does_not_excuse_an_unrelated_command():
    """The forward cue is scoped to a short trailing window on purpose — an
    outcome phrase describing a *different* sentence must not launder this one."""
    assert _is_claim(
        "run pip install contextlint now; a later step in this guide will fail if you skip it"
    )


def test_punctuation_after_the_package_name_still_matches():
    """Regression: a trailing backtick or comma used to break the match
    entirely, so the negation guard never got a chance to run at all."""
    assert CLAIM.search("run `pip install contextlint` now")
    assert CLAIM.search("run pip install contextlint, then verify")
    assert CLAIM.search("run pip install contextlint.")
