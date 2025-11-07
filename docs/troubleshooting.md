# Troubleshooting

Short answers to the most common errors. Each entry lists the symptom, likely cause, and the fastest fix.

## Missing `OPENAI_API_KEY`
- **Symptom:** CLI exits with `Missing environment variable OPENAI_API_KEY`.
- **Cause:** Env var not exported or running under a different shell.
- **Fix:** `export OPENAI_API_KEY=sk-...` (plus restart your terminal). On CI, add it to the job’s secret store.

## MCP Server Not Found
- **Symptom:** `Agent references unknown MCP server 'context7'` during `--run-agent`.
- **Cause:** `mcp_servers.context7` block missing or misspelled.
- **Fix:** Add the server definition to `codex_sub_agents.toml`, then rerun `codex-sub-agent --list-agents`.

## Codex `codex/event` Noise
- **Symptom:** Python MCP client logs “Unknown notification codex/event”.
- **Cause:** Codex CLI emits telemetry that the generic MCP client doesn’t understand.
- **Fix:** Use a wrapper command that filters those events (e.g., update `[mcp_servers.codex].command` to point to your custom helper) or ignore the warnings—they are harmless but verbose.

## GitHub MCP 401 Errors
- **Symptom:** `401 Unauthorized` when calling GitHub tools.
- **Cause:** Missing or expired `GITHUB_PERSONAL_ACCESS_TOKEN`.
- **Fix:** Generate a PAT with `repo`, `workflow`, and `read:org`, set it via `export GITHUB_PERSONAL_ACCESS_TOKEN=...`, and restart the agent.

## MCP Timeout / Hanging
- **Symptom:** CLI waits forever after launching an agent; no output.
- **Cause:** External MCP server still downloading dependencies or waiting for auth.
- **Fix:** Increase `client_session_timeout_seconds`, confirm the command runs manually, and check local firewalls.

## Logs & Diagnostics
- Codex CLI writes verbose logs under `.codex/log/`.
- The sub-agent prints failures to stderr; rerun with `--run-agent` for easier reproduction.
- `MCP_TRACE=debug` (env var) enables low-level protocol logging when using OpenAI’s Agents SDK.
