## What & Why

<!-- What changed and why. Link the issue/story. -->

Fixes #

## Type

- [ ] `feat` — New feature
- [ ] `fix` — Bug fix
- [ ] `refactor` — Code restructure (no behavior change)
- [ ] `docs` — Documentation only
- [ ] `test` — Test additions/updates
- [ ] `chore` — Dependencies, CI, cleanup

## Risk / Impact

- [ ] Low — Isolated change, no breaking impact
- [ ] Medium — Touches shared code or contracts
- [ ] High — Breaking change, migration required

## Testing

- [ ] New/updated unit tests
- [ ] All existing tests pass (`pytest tests/`)
- [ ] Linter clean (`ruff check src/ tests/`)
- [ ] Formatter clean (`ruff format --check src/ tests/`)
- [ ] Type check clean (`ty check`)

## Security Checklist

- [ ] No secrets in code, config, or logs
- [ ] User inputs validated and sanitized
- [ ] Dependencies scanned (`pip-audit`)
- [ ] Error messages don't expose internal details

## Pre-Merge

- [ ] PR is < 400 lines (or justified)
- [ ] Commit messages follow conventional commits
- [ ] Documentation updated (if applicable)
