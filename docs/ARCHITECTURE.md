# ADO Workflows MCP Server — Design & Architecture

## Problem

AI agents (Copilot, Claude, etc.) need to interact with Azure DevOps — discover
repositories, manage pull requests, check review status, post comments — but the
Azure DevOps SDK is complex and error-prone. Raw SDK calls leak implementation
details and produce unhelpful error messages.

## Solution

An MCP server that exposes the [ado-workflows](https://github.com/grimlor/ado-workflows)
library as tool calls. The server handles SDK orchestration, error translation,
and session state — agents see clean tools with structured inputs and outputs.

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│  AI Agent (Copilot / Claude / any MCP client)                │
│     │                                                        │
│     ▼                                                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ado-workflows-mcp (MCP Tool Layer)                    │  │
│  │                                                        │  │
│  │  repository_discovery()  → scan for ADO repos          │  │
│  │  set_repository_context()→ cache org/project/repo      │  │
│  │  establish_pr_context()  → resolve PR URL or ID        │  │
│  │  create_pull_request()   → create PR with validation   │  │
│  │  get_pr_review_status()  → votes + stale detection     │  │
│  │  analyze_pr_comments()   → categorize threads          │  │
│  │  post_pr_comment()       → new comment thread          │  │
│  │  reply_to_pr_comment()   → reply to existing thread    │  │
│  │  resolve_pr_comments()   → batch-resolve threads       │  │
│  └────────────────────────────────────────────────────────┘  │
│     │                                                        │
│     ▼                                                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ado-workflows (Library Layer)                         │  │
│  │                                                        │  │
│  │  ConnectionFactory, inspect_git_repository(),          │  │
│  │  PR operations, review queries, comment management     │  │
│  └────────────────────────────────────────────────────────┘  │
│     │                                                        │
│     ▼                                                        │
│  Azure DevOps REST API (via azure-devops SDK)                │
└──────────────────────────────────────────────────────────────┘
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Architecture** | Thin MCP wrapper over library | All logic in `ado-workflows`; server is glue |
| **Error strategy** | Errors as data, not exceptions | MCP transport stays clean; agents get structured recovery |
| **Session state** | In-memory context cache | Avoids redundant git CLI / SDK lookups per conversation |
| **Auth delegation** | `DefaultAzureCredential` via library | Server never touches credentials directly |
| **Tool granularity** | One tool per user intent | Agents reason better with focused, composable tools |

## Error Propagation

```
ado-workflows raises ActionableError
    → MCP tool catches it
    → Enriches with ai_guidance (if not already set)
    → Returns error dict via MCP transport

Unexpected Exception
    → MCP tool catches it
    → Wraps in ActionableError with ai_guidance
    → Returns error dict via MCP transport
```

Every tool function follows this pattern:
1. Validate inputs
2. Call `ado-workflows` library
3. Return success dict or `ActionableError.to_dict()`

No exceptions escape to the MCP transport layer.

## Three-Audience Error Design

Each error serves three audiences simultaneously:

| Field | Audience | Purpose |
|-------|----------|---------|
| `error` | Developer | Technical description of what went wrong |
| `suggestion` | End user | Actionable next step in plain language |
| `ai_guidance` | AI agent | Machine-readable recovery instructions |

The `ai_guidance` field contains structured hints: `action_required`, `checks`,
`steps`, `command`, and `discovery_tool` — enabling agents to self-recover
without human intervention.

## Files

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
