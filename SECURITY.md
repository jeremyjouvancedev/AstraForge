# Security Policy

## Reporting a vulnerability

Please email `jeremy.jouvance@gmail.com` with a description of the issue, steps to reproduce, and any proof-of-concept or logs. Avoid filing public issues or PRs for vulnerabilities.

If preferred, you can also open a private GitHub Security Advisory for the repository so we can coordinate fixes discreetly.

## What to expect

- We will acknowledge receipt within 3 business days.
- We will provide a remediation plan or request additional detail.
- Once a fix is ready, we will publish patched images and update the Python package as needed before disclosing the issue.

## Scope

- The `main` branch and published Docker images (`astraforge`, `astraforge-backend`, `astraforge-frontend`, `astraforge-llm-proxy`, `astraforge-codex-cli`, `astraforge-sandbox`).
- The published `astraforge-toolkit` Python package.

## Hardening checklist for reports

- Include affected configuration (auth mode, env vars, provisioner, executor).
- Share minimal reproduction steps and expected impact.
- Note whether data exposure, workspace escape, or privilege escalation is possible.
