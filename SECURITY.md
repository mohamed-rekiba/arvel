# Security Policy

Arvel takes security seriously. If you find a vulnerability, please follow the disclosure process below.

## Supported Versions

While the project is pre-1.0 (`0.x`), only the **latest minor release** receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.x.x   | latest minor only |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security reports.** Instead, use one of:

1. **GitHub Security Advisories** — [Report a vulnerability](https://github.com/<org>/arvel/security/advisories/new) (preferred)
2. **Email** — `security@<arvel-domain>` (PGP key on request)

Include:

- A description of the issue
- Steps to reproduce, including a minimal repro repository if possible
- The version of Arvel, Python, and any relevant dependencies
- The impact you believe the issue has

We aim to:

- Acknowledge receipt within **2 business days**
- Provide a triage assessment within **5 business days**
- Ship a fix or workaround for **critical** issues within **48 hours** once reproduced
- Coordinate disclosure on a mutually agreed timeline

## Scope

In scope:

- The `arvel` framework and its public API
- The `arvel` CLI (including the `new` command)
- Default scaffolding produced by `arvel new`

Out of scope:

- Vulnerabilities in third-party packages (please report to those projects directly; Arvel will track CVEs via dependabot + pip-audit)
- Issues that require local code execution as a precondition
- Self-XSS / social-engineering scenarios

## Hardening Built In

Arvel already enforces, at every release:

- `bandit` SAST gate (low severity threshold)
- `pip-audit` SCA gate on the resolved environment
- `gitleaks` secret scan on every PR and full repo history
- `semgrep` SAST gate (auto config + OWASP Top 10 + Python)
- CycloneDX SBOM generated per release artifact
- Sigstore keyless signing of all PyPI artifacts via Trusted Publishing
- Dependency updates via Dependabot (weekly)
- `mypy --strict` and `pyright --strict` parity

See the [DevSecOps pipeline](./.github/workflows/security.yml) for the full gate list.
