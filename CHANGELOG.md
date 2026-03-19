# CHANGELOG

<!-- version list -->

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
