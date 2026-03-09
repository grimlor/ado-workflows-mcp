# Contributing

Thanks for your interest in contributing to ado-workflows-mcp. This document
covers the development setup, coding standards, testing philosophy, and
PR process.

---

## Development Setup

```bash
# Clone
git clone https://github.com/grimlor/ado-workflows-mcp.git
cd ado-workflows-mcp

# Install with dev dependencies (creates .venv automatically)
uv sync --extra dev

# Optional: auto-activate venv
direnv allow
```

## Running Checks

All checks must pass before submitting a PR:

```bash
task check          # runs lint → type → test
```

Or individually:

```bash
task lint           # ruff check src/ tests/
task format         # ruff format src/ tests/
task type           # pyright type checking
task test           # pytest -v
task cov            # pytest with coverage report
```

## Code Style

- **Python 3.12+** — use modern syntax (`X | Y` unions, `@dataclass`).
- **`from __future__ import annotations`** at the top of every module.
- **ruff** handles formatting and import sorting. Don't fight it.
- **pyright** — all functions need type annotations. No `Any` unless
  you have a good reason and document it.
- **Line length:** 99 characters (configured in `pyproject.toml`).
- **Quote style:** double quotes.

## Testing Standards

Tests are the living specification. Every test class documents a behavioral
requirement, not a code structure.

### Test Class Structure

```python
class TestYourFeature:
    """
    REQUIREMENT: One-sentence summary of the behavioral contract.

    WHO: Who depends on this behavior (calling code, operator, AI agent)
    WHAT: What the behavior is, including failure modes
    WHY: What breaks if this contract is violated

    MOCK BOUNDARY:
        Mock:  ado_workflows SDK functions (library I/O edge)
        Real:  tool functions, error construction, AIGuidance
        Never: construct expected output and assert on the construction
    """

    def test_descriptive_name_of_scenario(self) -> None:
        """
        Given some precondition
        When an action is taken
        Then an observable outcome occurs
        """
        ...
```

### Key Principles

1. **Mock I/O boundaries, not implementation.** Mock the `ado-workflows`
   library functions — never mock internal helpers or dataclass construction.

2. **Failure specs matter.** For every happy path, ask: what goes wrong?
   Write specs for those failure modes. An unspecified failure is an
   unhandled failure.

3. **Missing spec = missing requirement.** If you find a bug, the first
   step is always adding the test that should have caught it, then fixing
   the code to pass that test.

4. **Every assertion includes a diagnostic message.** Bare assertions are
   not permitted.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the tool layers,
error propagation, and design decisions.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat: add repository context caching with session persistence

- set_repository_context() validates and caches org/project/repo
- get_repository_context_status() surfaces cached state for debugging
- clear_repository_context() resets to force fresh discovery
```

Common prefixes: `feat:`, `fix:`, `test:`, `docs:`, `build:`, `refactor:`,
`style:`, `ci:`, `chore:`.

## Pull Requests

1. **Branch from `main`.**
2. **All checks must pass** — `task check` (lint + type + test).
3. **Include tests** for any new behavior or bug fix.
4. **One concern per PR** — don't mix a new feature with unrelated refactoring.
5. **Describe what and why** in the PR description.

## Reporting Issues

When filing an issue:

- **Bug:** Include the error message, what you expected, and steps to
  reproduce. Include the Python version and how ado-workflows-mcp was
  installed.
- **Feature request:** Describe the problem you're trying to solve, not
  just the solution you have in mind.
