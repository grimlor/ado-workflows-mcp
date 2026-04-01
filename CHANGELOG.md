# CHANGELOG

<!-- version list -->

## v0.6.1 (2026-04-01)

### Bug Fixes

- **deps**: Bump ado-workflows floor to >=0.6.0 for CommentType.DOMAIN
  ([`feba94a`](https://github.com/grimlor/ado-workflows-mcp/commit/feba94a0da2b27f295b6545f8e13be0da5fa59e0))

### Testing

- Add branch coverage for pr_lifecycle ai_guidance pass-through
  ([`1fae11f`](https://github.com/grimlor/ado-workflows-mcp/commit/1fae11f36dfc96199e460b12d7fb92ae3b04a506))


## v0.6.0 (2026-04-01)

### Chores

- Update uv.lock
  ([`81a073e`](https://github.com/grimlor/ado-workflows-mcp/commit/81a073e28ad2b4a128f0a923396e757a938b975f))

### Features

- Add PR lifecycle MCP tools, rename pull_requests to pr_context
  ([`9db85cc`](https://github.com/grimlor/ado-workflows-mcp/commit/9db85cce2bd7844529710663ee584914961df65d))

### Breaking Changes

- `tools/pull_requests.py` renamed to `tools/pr_context.py` for consistent `pr_*` module naming.
  Consumers importing from `ado_workflows_mcp.tools.pull_requests` must update to
  `ado_workflows_mcp.tools.pr_context`.


## v0.5.1 (2026-03-30)

### Bug Fixes

- **ci**: Install uv via pipx instead of curl in .envrc
  ([`accd75e`](https://github.com/grimlor/ado-workflows-mcp/commit/accd75e09572c2e59712999a7bf03c5496d4dd9f))

### Refactoring

- **tests**: Fix mock boundary violations across test suite\n\nRemove 19 mocks of internal library
  functions (_lib_establish_pr,\n_lib_establish, _lib_post_rich, get_client,
  _lib_current_user)\nacross 6 test files. Replace with proper I/O boundary mocks:\n\n- Pattern A:
  Use invalid input (pr_url_or_id=\"not-a-valid-id\") to\n trigger real
  ActionableError.validation(ai_guidance=None) for\n enrichment tests — zero mocks needed.\n-
  Pattern B: Mock ConnectionFactory.get_connection to raise\n RuntimeError/TypeError for unexpected
  exception tests.\n- Pattern C: Let real library run through mocked SDK for argument\n coercion
  tests, verify via RichPostingResult output.\n\nAlso add create_comment mock to
  _mock_client_for_posting() to\nsupport parent_thread_id reply path.\n\n93 tests, 334 stmts, 0
  missed, 100% coverage."
  ([`65420f6`](https://github.com/grimlor/ado-workflows-mcp/commit/65420f645477fc81c6f02233d29f4d3e51c7c205))


## v0.5.0 (2026-03-30)

### Features

- **tools**: Add post_rich_comments MCP tool\n\n- Add post_rich_comments tool with string-to-enum
  coercion at MCP boundary\n- Bump ado-workflows dependency to >=0.4.0 (PyPI release with rich
  models)\n- Add 11 BDD tests covering coercion, validation, error handling\n- Remove dead
  enrichment branch in get_current_user (pr_identity)\n- Rename _get_client/_get_context to
  get_client/get_context — module name\n _helpers.py is the visibility boundary, not function
  prefixes\n- Update _helpers.py docstring to document naming convention\n- 100% coverage maintained
  (334 stmts, 0 missed, 93 tests)
  ([`0f16164`](https://github.com/grimlor/ado-workflows-mcp/commit/0f16164458a93168b92502a680f78693f805e314))


## v0.4.2 (2026-03-27)

### Bug Fixes

- **tools**: Derive org_url from PR context instead of repo context
  ([`ffadcf4`](https://github.com/grimlor/ado-workflows-mcp/commit/ffadcf4b5783f01170328d93c8a0ff82def624d7))


## v0.4.1 (2026-03-27)

### Bug Fixes

- **deps**: Require ado-workflows>=0.3.0 for exclude_extensions
  ([`28e8d22`](https://github.com/grimlor/ado-workflows-mcp/commit/28e8d22f95bcccc4a4dbae1a0c31a13e4b4599b1))


## v0.4.0 (2026-03-27)

### Chores

- **lint**: Add pydocstyle rules and fix docstring issues
  ([`313c6be`](https://github.com/grimlor/ado-workflows-mcp/commit/313c6bed3527ad2bb77ca55ad726b9f82a6fe1f4))

### Features

- **pr_files**: Expose exclude_extensions parameter in get_pr_file_contents
  ([`5ccf746`](https://github.com/grimlor/ado-workflows-mcp/commit/5ccf746083c3d33358d9f414470d32ff3ba21901))


## v0.3.0 (2026-03-19)

### Features

- **tools**: Add get_pr_author and get_current_user identity tools
  ([`469ad22`](https://github.com/grimlor/ado-workflows-mcp/commit/469ad22291412f24b368451e33189c0ba3b15552))


## v0.2.0 (2026-03-19)

### Build System

- Add upload_to_pypi = false to align with other repos
  ([`f061c59`](https://github.com/grimlor/ado-workflows-mcp/commit/f061c59b85b3d2d6682bbd77c8e2fddb19ce932a))

### Features

- **tools**: Add batch comment posting, file changes, and file contents tools
  ([`9b1c898`](https://github.com/grimlor/ado-workflows-mcp/commit/9b1c898dd94b3afa2636bcb71591945061b0b1ce))


## v0.1.3 (2026-03-19)

### Bug Fixes

- **ci**: Use PAT for release push to bypass branch ruleset
  ([`269f8e3`](https://github.com/grimlor/ado-workflows-mcp/commit/269f8e3619398086645ba11a0aa62ad91140d6f2))

### Build System

- Remove CI skill sync in favor of universal-dev-skills clone
  ([`59cd8fe`](https://github.com/grimlor/ado-workflows-mcp/commit/59cd8fe0292adb93337435c74b347ae0482aef49))

### Chores

- Add format step to check task
  ([`0afe6db`](https://github.com/grimlor/ado-workflows-mcp/commit/0afe6db29ac66070b4a18492aed73e68bc1d61d8))

- Add license badge, normalize badge format
  ([`7084bd4`](https://github.com/grimlor/ado-workflows-mcp/commit/7084bd422df76e419739e4f388a7ce19003bd7ea))

- Add ruff per-file-ignores for test conventions
  ([`2ba39ea`](https://github.com/grimlor/ado-workflows-mcp/commit/2ba39eab3cd76adf7789ee8034eb4e72ed5ef41e))

- Cap requires-python, add pytest markers, normalize gitignore, add PUBLISHING.md, unify PR template
  ([`1a9bdda`](https://github.com/grimlor/ado-workflows-mcp/commit/1a9bdda311777bdfd05ea20e28209422a5aca5b7))


## v0.1.2 (2026-03-10)

### Bug Fixes

- Remove global pyright suppressions, add inline pragmas
  ([`9bc9cab`](https://github.com/grimlor/ado-workflows-mcp/commit/9bc9cab8205ef1aad89fa1a506c9a9528943496c))

### Chores

- Standardize author identity, add skills and sync workflow
  ([`4bc9f4f`](https://github.com/grimlor/ado-workflows-mcp/commit/4bc9f4fdfc63027c56703605d8f73bf9d59ebbd4))


## v0.1.1 (2026-03-10)

### Bug Fixes

- Add concrete return types to all tool functions for outputSchema generation
  ([`8d23b53`](https://github.com/grimlor/ado-workflows-mcp/commit/8d23b535c557a1c1d43da5fab6b17456ff20bf13))

- Narrow union return type before .get() call in test
  ([`886f6e5`](https://github.com/grimlor/ado-workflows-mcp/commit/886f6e5b014713577cec927dc1ce08d3eab17a12))

- Sort imports and suppress TC002 for runtime-required model types
  ([`812d059`](https://github.com/grimlor/ado-workflows-mcp/commit/812d059cb19ff1e268c94ca22e6cd83d6e02c4bc))

- **ci**: Push release commit to main alongside tag
  ([`aed7442`](https://github.com/grimlor/ado-workflows-mcp/commit/aed74425ffc615762489b2ae21db13b84f17b04e))

### Chores

- Remove accidentally committed junk file
  ([`fb33bbb`](https://github.com/grimlor/ado-workflows-mcp/commit/fb33bbba414af70923a4f19973a187d88d9295c4))

### Testing

- Close coverage gap — 60 tests, 100% coverage
  ([`f3698bc`](https://github.com/grimlor/ado-workflows-mcp/commit/f3698bce6f46ea077b8f4f12747df8e617bce3d8))


## v0.1.0 (2026-03-09)

- Initial Release
