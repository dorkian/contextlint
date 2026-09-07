# Releasing

`contextlint` (the tool, the repo, the installed command) is published on PyPI as of v0.1.1. A
CI job runs `scripts/check_install_claims.py`, which fails the build if any fenced command in
the docs promises a bare install of a name PyPI doesn't actually serve.

**The PyPI distribution name is `dorkian-context-lint`, not `contextlint`.** PyPI's
registration-time namespace-similarity check rejects the shorter name outright — a plain GET
against the JSON API returns 404 either way, so that rejection is invisible until you actually
try to register it. Nothing else changes: the repo, the CLI command, and every mention of
"contextlint" elsewhere in this project stay exactly as they are.

Because the names permanently differ, the README's install section can never fully collapse to
a bare `uvx contextlint` — `uvx <name>` assumes the package name matches the command name by
default. The real short form, live today, is `uvx --from dorkian-context-lint contextlint` (see
`scripts/check_install_claims.py`'s docstring for exactly what the guard allows and why).

<details>
<summary><b>What actually happened with v0.1.0</b></summary>

<br>

It doesn't exist as an installable release, and never will. The tag was cut from a commit before
`pyproject.toml`'s name was corrected, so `release.yml` built a package still called
`contextlint` and tried to upload it against a pending publisher already registered for
`dorkian-context-lint` — PyPI rejected it: `400 Non-user identities cannot create new projects.
This was probably caused by successfully using a pending publisher but specifying the project
name incorrectly`. The pending publisher had already claimed the project *name* on PyPI by that
point (which is why `https://pypi.org/simple/dorkian-context-lint/` returned a real, empty page
rather than 404), but zero files were ever uploaded — `pip install dorkian-context-lint` 404'd
on "no matching distribution" until v0.1.1 shipped for real. If a future release ever fails
after the name has claimed its slot on PyPI, check the simple index directly
(`pypi.org/simple/dorkian-context-lint/`) rather than trusting the JSON API or the project page
alone — both can look "live" before any file has actually landed.

</details>

## One-time setup (must be done by a PyPI account owner)

Publishing uses **Trusted Publishing**, so no API token is ever stored in this repository. PyPI
verifies the GitHub Actions workflow's identity over OIDC instead. That removes exactly the kind
of long-lived credential this tool flags in other people's configs.

1. Create a PyPI account and enable 2FA — <https://pypi.org/account/register/>
2. Go to <https://pypi.org/manage/account/publishing/> and add a **pending publisher**:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `dorkian-context-lint` |
   | Owner | `dorkian` |
   | Repository name | `contextlint` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   "Pending" is correct for a project's first-ever publish — the name doesn't exist on PyPI yet,
   and the first successful run creates it. Already done for `dorkian-context-lint`; this section
   is for setting up a fork or a from-scratch equivalent.

3. In this repository, create the environment GitHub Actions will publish from:
   **Settings → Environments → New environment → `pypi`**.
   Optionally add yourself as a required reviewer, which makes every publish need one click.

That is the whole setup. Nothing is copied into repository secrets.

## Cutting a release

```bash
# 1. bump the version in pyproject.toml and src/contextlint/__init__.py
#    (both must agree; CI checks the tag against pyproject)
# 2. refresh anything measured, so the README cannot drift from the release
python benchmarks/run.py
uv run --no-project --with tiktoken python benchmarks/calibrate.py
python docs/assets/make_charts.py
python docs/assets/make_brand.py

# 3. commit, tag, push — pick the next version; tags are never reused or moved
git commit -am "Release v0.1.2"
git tag v0.1.2
git push origin main --tags
```

The tag triggers `release.yml`, which:

1. refuses to continue if the tag and `pyproject.toml` disagree,
2. runs the full test suite and the benchmark harness,
3. builds and `twine check`s the artifacts,
4. publishes to PyPI over OIDC,
5. creates a GitHub release with generated notes and the built artifacts attached.

Nothing reaches PyPI unless the tests and the benchmarks pass first.

## Testing the pipeline without publishing for real

Add a TestPyPI pending publisher the same way at
<https://test.pypi.org/manage/account/publishing/>, then run the workflow manually with
`workflow_dispatch`. The publish job is gated on `startsWith(github.ref, 'refs/tags/v')`, so a
manual run builds and verifies without pushing anything.
