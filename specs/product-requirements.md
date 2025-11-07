# Product Requirements – Codex Sub-Agent

## Overview
Codex Sub-Agent packages reusable MCP workflows so engineers can install Codex CLI, register supporting servers (Context7, GitHub, etc.), and get back to shipping. The experience must optimize for newcomers who are time-starved yet responsible for clean automation setups.

## Goals
1. **Fast first install (Priority A):** Someone new to the repo can install, configure, and run the smoke-test agent in under 10 minutes.
2. **Confident multi-server configuration (Priority B):** Power users can add/adjust MCP servers and agents without breaking existing workflows.
3. **Actionable troubleshooting (Priority D):** When things fail, users can identify the root cause and apply the fix within five minutes.

## Personas
- **Ops Engineer Onboarding Codex:** Owns CI/CD and needs repeatable setup steps.
- **Staff Developer Extending Workflows:** Adds new MCP integrations and guards against regressions.
- **Support Engineer Diagnosing MCP Errors:** Triages incidents and needs precise recovery guidance.

## Core User Stories
- **A1:** As an onboarding engineer, I need copy/pasteable install steps so that I can verify Codex Sub-Agent locally without guesswork. _Acceptance:_ quickstart includes prerequisites, install commands, config copy, and validation.
- **A2:** As the same engineer, I need a verification command so that I know the install succeeded. _Acceptance:_ `--list-agents` and `--run-agent csa:test-agent` documented with expected output.
- **B1:** As a staff developer, I need a schema reference for MCP servers so that I can add new entries safely. _Acceptance:_ configuration doc lists required keys, defaults, and validation tips.
- **B2:** As the developer, I need alias/tool guidance so that Codex users see stable tool names. _Acceptance:_ documentation explains alias-to-tool sanitization and the per-agent directory structure (`agent.toml`, Markdown instructions/entry).
- **D1:** As a support engineer, I need symptom-based troubleshooting so that I can map errors to fixes quickly. _Acceptance:_ troubleshooting doc includes missing env vars, MCP timeouts, GitHub auth, and Codex-specific noise.

## Success Metrics
- < 10% of new installs require human support.
- Average time to resolve MCP config issues < 5 minutes using docs alone.
- Documentation engagement: quickstart and configuration pages account for 80% of doc visits (indicating discoverability).

## Out of Scope
- Day-to-day workflow automation guidance (covered by project-specific instructions).
- Automated configuration editors or GUIs.
