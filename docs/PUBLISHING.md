# Publishing to PyPI

## How It Works

Publishing is fully automated via **python-semantic-release** (PSR) and
**PyPI Trusted Publishers** (OIDC) — no API tokens or manual version bumps needed.

When a commit lands on `main` with a conventional commit prefix (`feat:`, `fix:`,
`feat!:`), PSR determines the next version, updates `pyproject.toml`, creates a
tag, and triggers the release workflow which builds and uploads to PyPI.

## One-Time Setup

1. Go to https://pypi.org/manage/account/publishing/
2. Add a **pending publisher** with:
   - **PyPI project name:** `ado-workflows-mcp`
   - **Owner:** `grimlor`
   - **Repository:** `ado-workflows-mcp`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
3. Create a GitHub Environment named `pypi` in the repo settings:
   - Settings → Environments → New environment → `pypi`

## Publishing a Release

Just merge to `main` with conventional commit messages:

```bash
git commit -m "feat: add new tool function"   # → minor bump
git commit -m "fix: handle edge case"          # → patch bump
git commit -m "feat!: redesign API"            # → major bump
```

The `release.yml` workflow will automatically:
1. Determine next version from commit messages
2. Update version in `pyproject.toml`
3. Create git tag and GitHub Release
4. Build wheel + sdist
5. Upload to PyPI via OIDC

## Local Build (for testing)

```bash
uv build
ls dist/
```

## Verification

After publishing:

```bash
pip install ado-workflows-mcp
```
