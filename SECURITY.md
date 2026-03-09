# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it
responsibly by emailing the maintainer directly rather than opening a public
issue.

## Scope

This MCP server delegates all Azure DevOps API access to the
[ado-workflows](https://github.com/grimlor/ado-workflows) library. Security
considerations:

- **Authentication delegation** — `ado-workflows` acquires OAuth tokens via
  `DefaultAzureCredential`. This server never handles credentials directly.
  Leaked tokens grant Azure DevOps API access.
- **Error propagation** — `ActionableError` instances may carry SDK exception
  messages containing URLs, project names, or repository identifiers.
  The server returns errors as structured data; consumers should apply
  `actionable_errors.sanitizer` before logging or exposing to end users.
- **Repository discovery** — `repository_discovery` reads git remote URLs
  from the local filesystem. In shared environments, ensure the working
  directory is trusted.

## Best Practices

- Use `DefaultAzureCredential` (managed identity in CI, Azure CLI locally)
  rather than hardcoded PATs
- Apply the `actionable-errors` credential sanitizer to error messages
  before exposing them to end users or external logging systems
- Do not log or persist raw OAuth tokens
