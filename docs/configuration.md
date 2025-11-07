# Configuration Reference

Use this guide when you need to tune agents, add MCP servers, or double-check schema fields.

## File Layout Recap

```
config/
  codex_sub_agents.toml        # root file referenced by Codex CLI
  agents/
    workflow/
      agent.toml
      instructions.md
      entry_message.md
    security_review/
      ...
    test_agent/
      ...
```

Set the `--config` flag on every CLI call so the loader knows which bundle to use. Each agent directory is self-contained, so copying or deleting a workflow only requires moving a single folder.

## OpenAI Block

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `api_key_env_var` | string | `OPENAI_API_KEY` | CLI validates the env var before launching any agent. |
| `default_api` | enum | `responses` | Must be `responses` or `chat_completions`. |

Keep the actual key in your shell environment or `.envrc`; never hardcode it inside the TOML file.

## MCP Servers

Every server appears under `[mcp_servers.<name>]`.

### STDIO Example (Codex CLI)
```toml
[mcp_servers.codex]
type = "stdio"
name = "Codex CLI"
command = "npx"
args = ["-y", "codex", "mcp-server"]
client_session_timeout_seconds = 360000
```
- `name` is human readable.
- `command` + optional `args` indicate how to launch the MCP server.
- For custom helpers, replace the command path and keep the same schema.

### HTTP Example (GitHub MCP)
```toml
[mcp_servers.github]
type = "http"
name = "GitHub"
url = "https://api.githubcopilot.com/mcp"
bearer_token_env_var = "GITHUB_PERSONAL_ACCESS_TOKEN"
client_session_timeout_seconds = 60
```
Headers can be set via the optional `headers = {"User-Agent" = "..."}` map.

## Agents & Aliases

Each agent directory defines:

```toml
# agents/workflow/agent.toml
id = "workflow"

[agent]
name = "Codex Workflow Sub-Agent"
model = "gpt-5"
reasoning_tokens = 4096
mcp_servers = ["codex", "context7", "github"]
```

Free-form text lives in Markdown files sitting next to the TOML:

- `instructions.md` for the long-form instructions block
- `entry_message.md` for the kickoff prompt shown to the workflow

Key tips:
- `mcp_servers` must reference names that exist under `[mcp_servers.*]`.
- `aliases` in the root config map user-friendly names to agent IDs:
  ```toml
  [aliases]
  "csa:default" = "workflow"
  ```
- Tool names exposed over MCP are auto-sanitized (e.g., `csa:test-agent` → `csa_test-agent`).

## Validating Changes

1. Run `codex-sub-agent --list-agents` to confirm IDs and aliases render as expected.
2. Dry-run a workflow locally:
   ```bash
   codex-sub-agent --config <path> --run-agent workflow --request "Summarize repo status"
   ```
3. Launch Codex CLI and ensure the new tool appears under `list_tools`.

If anything fails, see `troubleshooting.md` for targeted fixes.
