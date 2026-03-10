# ADO Workflows MCP Server

[![CI](https://github.com/grimlor/ado-workflows-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/grimlor/ado-workflows-mcp/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/grimlor/b7836cded70590f934b1877fd521c26b/raw/ado-workflows-mcp-coverage-badge.json)](https://github.com/grimlor/ado-workflows-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ado-workflows-mcp)](https://pypi.org/project/ado-workflows-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

An MCP server exposing [ado-workflows](https://github.com/grimlor/ado-workflows)
as tool calls for AI agents. Enables Copilot and other MCP clients to discover
Azure DevOps repositories, manage pull requests, and interact with PR comments
and reviews.

## Quick Install

[<img src="https://img.shields.io/badge/VS_Code-VS_Code?style=flat-square&label=Install%20Server&color=0098FF" alt="Install in VS Code">](https://vscode.dev/redirect?url=vscode%3Amcp%2Finstall%3F%257B%2522name%2522%253A%2520%2522ado-workflows-mcp%2522%252C%2522command%2522%253A%2520%2522uvx%2522%252C%2522args%2522%253A%2520%255B%2522--from%2522%252C%2522git%252Bhttps%253A%252F%252Fgithub.com%252Fgrimlor%252Fado-workflows-mcp%2522%252C%2522ado-workflows-mcp%2522%255D%252C%2522type%2522%253A%2520%2522stdio%2522%257D) [<img alt="Install in VS Code Insiders" src="https://img.shields.io/badge/VS_Code_Insiders-VS_Code_Insiders?style=flat-square&label=Install%20Server&color=24bfa5">](https://insiders.vscode.dev/redirect?url=vscode-insiders%3Amcp%2Finstall%3F%257B%2522name%2522%253A%2520%2522ado-workflows-mcp%2522%252C%2522command%2522%253A%2520%2522uvx%2522%252C%2522args%2522%253A%2520%255B%2522--from%2522%252C%2522git%252Bhttps%253A%252F%252Fgithub.com%252Fgrimlor%252Fado-workflows-mcp%2522%252C%2522ado-workflows-mcp%2522%255D%252C%2522type%2522%253A%2520%2522stdio%2522%257D)

*Click a badge above to install with one click, or follow manual installation
below.*

## Features

- **Repository Discovery**: Scan directories for git repos with Azure DevOps remotes
- **PR Lifecycle**: Create pull requests, establish PR context from URLs or IDs
- **Review Management**: Check reviewer votes, detect stale approvals, find PRs needing attention
- **Comment Workflows**: Analyze, post, reply to, and batch-resolve PR comment threads
- **Session Caching**: Cache repository context to avoid redundant git CLI lookups
- **Error Handling**: Actionable errors with suggestions via [actionable-errors](https://github.com/grimlor/actionable-errors)

## MCP Tools

### Repository Discovery

| Tool | Description |
|------|-------------|
| `repository_discovery` | Scan a directory for git repos with Azure DevOps remotes, select the best match |
| `set_repository_context` | Cache repository context for the session (avoids redundant git CLI lookups) |
| `get_repository_context_status` | Inspect current cached context state for debugging |
| `clear_repository_context` | Reset cached context, forcing fresh discovery |

### Pull Requests

| Tool | Description |
|------|-------------|
| `establish_pr_context` | Parse a PR URL or resolve a numeric PR ID into reusable context |
| `create_pull_request` | Create a new PR from branch names with optional title, description, and draft mode |

### PR Review

| Tool | Description |
|------|-------------|
| `get_pr_review_status` | Fetch reviewer votes, commit history, and detect stale approvals |
| `analyze_pending_reviews` | Discover PRs needing review attention across a repository |

### PR Comments

| Tool | Description |
|------|-------------|
| `analyze_pr_comments` | Categorize comment threads by status with author statistics |
| `post_pr_comment` | Post a new comment thread to a PR |
| `reply_to_pr_comment` | Reply to an existing comment thread |
| `resolve_pr_comments` | Batch-resolve comment threads (partial-success semantics) |

## Installation

### Quick Install (Recommended)

Click one of the badges at the top to automatically install in VS Code!

### Manual Installation

```bash
cd ado-workflows-mcp
uv sync --all-extras
```

## VS Code / Copilot Configuration

Add to your VS Code settings or `.vscode/mcp.json`:

```json
{
  "mcp.servers": {
    "ado-workflows": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/grimlor/ado-workflows-mcp", "ado-workflows-mcp"],
      "description": "Azure DevOps workflow automation tools"
    }
  }
}
```

The server communicates over stdio using the [Model Context Protocol](https://modelcontextprotocol.io/).

## Authentication

Uses Azure `DefaultAzureCredential` via the [ado-workflows](https://github.com/grimlor/ado-workflows) library. Authenticate with any method that `DefaultAzureCredential` supports:

```bash
az login                           # Azure CLI (local dev)
az login --use-device-code         # Headless / SSH
```

Managed identity, environment variables, and other credential providers work automatically in hosted environments.

## Error Handling

All errors are returned as structured [`ActionableError`](https://github.com/grimlor/actionable-errors) objects with:

- **`error`** / **`suggestion`** — human-readable context
- **`ai_guidance`** — machine-readable recovery instructions (`action_required`, `checks`, `steps`, `command`, `discovery_tool`)

Errors are returned as data, never raised — the MCP transport stays clean.

## Typical Workflow

```
1. repository_discovery        → find the ADO repo
2. set_repository_context      → cache it for the session
3. establish_pr_context        → resolve a PR URL or ID
4. get_pr_review_status        → check approval state
5. analyze_pr_comments         → see active threads
6. post_pr_comment / reply     → leave feedback
7. resolve_pr_comments         → mark threads as fixed
```

## Development

```bash
uv run task check                # lint + type + test (all-in-one)
uv run task test                 # Run tests (37 BDD specs)
uv run task cov                  # Run tests with coverage
uv run task lint                 # Lint (with auto-fix)
uv run task format               # Format code
uv run task type                 # Type check
```

> **Note:** `uv run` is optional when the venv is activated via direnv.

### Project Structure

```
src/ado_workflows_mcp/
├── server.py              # FastMCP server entry point
├── mcp_instance.py        # MCP singleton
├── tools/
│   ├── repositories.py    # Repository discovery tools
│   ├── repository_context.py  # Session context management
│   ├── pull_requests.py   # PR lifecycle tools
│   ├── pr_review.py       # Review status tools
│   ├── pr_comments.py     # Comment workflow tools
│   └── _helpers.py        # Shared error-handling utilities
└── py.typed               # PEP 561 marker
```

## Testing

**37 BDD specs across 10 requirement classes** — organized by consumer requirement,
not code structure.

| Requirement Class | Specs | Coverage |
|---|---|---|
| TestRepositoryDiscovery | 3 | Success, working-dir failure, SDK failure |
| TestSetRepositoryContext | 3 | Valid context, missing fields, SDK failure |
| TestGetRepositoryContextStatus | 3 | Populated, empty, error |
| TestClearRepositoryContext | 2 | Reset + clear state |
| TestEstablishPRContext | 3 | URL parse, ID resolve, SDK failure |
| TestCreatePullRequest | 3 | Success, missing branch, SDK failure |
| TestGetPRReviewStatus | 3 | Success, invalid PR, SDK failure |
| TestAnalyzePendingReviews | 3 | Results, empty, SDK failure |
| TestAnalyzePRComments | 3 | Categorized, no threads, SDK failure |
| TestPostPRComment | 3 | Valid post, empty content, SDK failure |
| TestReplyToPRComment | 3 | Valid reply, missing thread, SDK failure |
| TestResolvePRComments | 3 | Batch resolve, empty list, SDK failure |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — Tool layers, error propagation, and design decisions

## Related

- [ado-workflows](https://github.com/grimlor/ado-workflows) — Azure DevOps automation library used by this server
- [actionable-errors](https://github.com/grimlor/actionable-errors) — Three-audience error framework
- [demo-assistant-mcp](https://github.com/grimlor/demo-assistant-mcp) — MCP server for demo script orchestration

## License

This project is licensed under the [MIT License](LICENSE).
