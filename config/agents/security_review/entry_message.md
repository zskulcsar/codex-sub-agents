Run a focused security review for the current repository snapshot.

Tasks:
1. Inventory authentication, authorization, and secrets handling logic; highlight any risky patterns.
2. Audit dependency manifests and lockfiles for outdated or vulnerable libraries, citing Context7 evidence.
3. Inspect CI/CD, container, and infrastructure scripts for insecure defaults.
4. Summarize findings in SECURITY_REVIEW.md with severity, evidence, and recommended mitigation steps.
5. Flag follow-up actions through the GitHub MCP server when manual remediation is required.

Constraints:
- Do not modify production credentials or rotate secrets automatically.
- Prefer actionable documentation and GitHub issues over speculative code edits.
