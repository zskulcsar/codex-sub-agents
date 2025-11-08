# Technical Specification – Codex Sub-Agent

## Architecture Summary
Codex Sub-Agent is a Python package that exposes configured workflows via two surfaces:
1. **Local CLI mode** – `codex-sub-agent --run-agent <alias>` loads the TOML bundle, starts only the MCP servers the agent requires, and runs the OpenAI Agents SDK workflow once.
2. **MCP server mode** – running `codex-sub-agent` without `--run-agent` starts an MCP server over stdio. Each alias is exposed as a tool; when a client calls the tool, the server spins up the referenced MCP servers, runs the agent, and streams the result back.

External dependencies: OpenAI API (Responses), Context7 MCP, GitHub MCP, and Codex CLI (spawned via `npx`).

## Components & Responsibilities
- `codex_sub_agent/cli.py`
  - Parses CLI args, dispatches configure/list/run flows.
  - Validates OpenAI credentials and routes agent runs to `Runner.run`.
  - Hosts the MCP server (using `mcp.server.Server`).
- `codex_sub_agent/config_loader.py`
  - Loads `codex_sub_agents.toml` plus per-agent directories.
  - Validates schema with Pydantic models (`AgentSettings`, `MCPStdioConfig`, `MCPHttpConfig`) and reads Markdown (`instructions.md`, `entry_message.md`) alongside `agent.toml`.
- `codex_sub_agent/codex_mcp_wrapper.py`
  - Optional helper that proxies `npx codex mcp-server` while filtering Codex-specific `codex/event` notifications.
- `config/` bundle
  - Ships default MCP server definitions, agent profiles, and aliases so a fresh install works instantly. Each agent directory contains `agent.toml`, `instructions.md`, and `entry_message.md`.

## Data & Control Flows
1. **CLI run:** user calls `codex-sub-agent --config path --run-agent alias` → CLI loads config → `AgentRegistry` resolves alias → `initialize_mcp_servers` starts required MCP servers → Agents SDK runs instructions with the provided entry message → CLI prints final output.
2. **MCP server:** CLI starts stdio server → registers tool definitions derived from aliases → on `call_tool`, same path as above but result returned as `CallToolResult` content.
3. **Configure helper:** `codex-sub-agent configure --config path` writes the `[mcp_servers.codex_sub_agent]` stanza into `.codex/config.toml` so Codex CLI can launch the sub-agent automatically.

## Configuration Schema Highlights
- **OpenAI block:** `api_key_env_var` (string), `default_api` (enum `responses`/`chat_completions`).
- **MCP servers:**
  - STDIO: `type`, `name`, `command`, optional `args`, `env`, `client_session_timeout_seconds`.
  - HTTP: `type`, `name`, `url`, optional `headers`, `bearer_token_env_var`, timeout.
- **Agents:** `id`, `name`, `model`, `temperature`, `reasoning_tokens`, `instructions`, `entry_message`, `mcp_servers`. Metadata lives in `agent.toml`; textual fields are sourced from Markdown files sitting next to it.
- **Aliases:** map of user-facing names to agent IDs; tool names are sanitized versions (non-alphanumeric replaced with `_`).
- **Environment sourcing:** before validating credentials, the CLI looks for `.envrc` in the current working directory and sources it with `bash` so missing variables like `OPENAI_API_KEY` are populated. Existing process values take precedence.

## Error Handling & Observability
- Missing env vars raise `RuntimeError` with clear messaging before touching the network.
- Invalid configuration raises `InvalidConfiguration` with the offending field.
- MCP server startup issues surface as immediate exceptions (e.g., missing bearer token).
- Troubleshooting doc instructs users to reference `.codex/log/` and set `MCP_TRACE=debug` as needed.

## Testing & Verification
- Pytest suite (`tests/test_cli.py`) covers `--list-agents`, configure idempotence, and `--run-agent` dispatch logic via monkeypatching.
- Future docs/specs validation can use Markdown link checkers or linting jobs.
- Manual smoke tests: follow `docs/quickstart.md`, run `codex-sub-agent --run-agent csa:test-agent`, then start Codex CLI and ensure the MCP tools appear.
