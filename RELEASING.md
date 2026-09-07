# Releasing

`contextlint` is not on PyPI yet. Until it is, the README documents git installs only — a CI
job (`documented install commands are true`) fails the build if any file promises a bare
`pip install contextlint` while PyPI does not actually serve it.

Publishing flips that on. After the first successful release the README's install section can
be simplified to `uvx contextlint`, and the guard will start allowing it automatically.

## One-time setup (must be done by a PyPI account owner)

Publishing uses **Trusted Publishing**, so no API token is ever stored in this repository. PyPI
verifies the GitHub Actions workflow's identity over OIDC instead. That removes exactly the kind
of long-lived credential this tool flags in other people's configs.

1. Create a PyPI account and enable 2FA — <https://pypi.org/account/register/>
2. Go to <https://pypi.org/manage/account/publishing/> and add a **pending publisher**:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `contextlint` |
   | Owner | `dorkian` |
   | Repository name | `contextlint` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   "Pending" is correct — the project does not exist on PyPI yet, and the first successful run
   creates it.

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

# 3. commit, tag, push
git commit -am "Release v0.1.0"
git tag v0.1.0
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
