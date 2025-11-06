# Codex Sub-Agent

This package ships a reusable sub-agent that exposes Codex CLI as an MCP server and augments it with Context7 documentation search and GitHub automation. Install it into any Codex-enabled environment and register it in `.codex/config.toml` to enable the workflow.

## Installation

```bash
uv pip install --system .
# or: pip install .
```

## Configuration

Copy the configuration bundle from the project’s root `config/` directory to your preferred location (for example `~/.config/codex/`), then adjust paths as needed:

- `codex_sub_agents.toml` defines shared OpenAI/MCP settings and references each agent via `agent_files`.
- `agents/workflow.toml` – general-purpose engineering workflow (set as the default agent).
- `agents/security_review.toml` – security auditor that documents findings in `SECURITY_REVIEW.md` and raises follow-up GitHub issues when needed.
- `agents/test_agent.toml` – lightweight smoke-test agent that simply confirms the configuration is wired up.

Paths listed under `agent_files` are resolved relative to the main TOML file, so moving the folder together keeps references intact. Add or remove agent files by editing that list; each agent file must declare an `id` plus an `[agent]` table with the usual fields (instructions, entry_message, etc.).

Expose stable mentions via the `[aliases]` table so Codex users can call agents by name:

```toml
[aliases]
"csa:default" = "workflow"
"csa:test-agent" = "test_agent"
"csa:security" = "security_review"
```

Inside Codex, run `agent csa:default`, `agent csa:test-agent`, or `agent csa:security` to dispatch the matching sub-agent without remembering internal IDs.

Set the following environment variables so the agent can authenticate:

- `OPENAI_API_KEY`
- `GITHUB_PERSONAL_ACCESS_TOKEN` (if you want access to the GitHub MCP server)

## Registering with Codex CLI

Add an entry to `.codex/config.toml`:

```toml
[mcp_servers.codex_sub_agent]
command = "codex-sub-agent"
args = ["--config", "/absolute/path/to/codex_sub_agents.toml"]
startup_timeout_sec = 60
client_session_timeout_seconds = 3600
```

Once registered you can call the agent from the Codex CLI (or other MCP-aware clients) and it will orchestrate Codex, Context7, and GitHub to complete the configured workflow.

## Running specific sub-agents

1. List the agent profiles defined in your config:
   ```bash
   codex-sub-agent --config ~/.config/codex/codex_sub_agents.toml --list-agents
   ```
2. Run the test agent to validate installation:
   ```bash
   codex-sub-agent --config ~/.config/codex/codex_sub_agents.toml --agent test_agent
   ```
   You should see `Codex sub-agent configuration is correct. You can now use sub agents!`
   (Inside an interactive Codex session, invoke `agent csa:test-agent` to trigger the same check.)
3. Run the default workflow agent (explicit):
   ```bash
   codex-sub-agent --config ~/.config/codex/codex_sub_agents.toml --agent workflow
   ```
   Equivalent Codex mention: `agent csa:default`
4. Run the security review agent with a custom kickoff request:
   ```bash
   codex-sub-agent \
     --config ~/.config/codex/codex_sub_agents.toml \
     --agent security_review \
     --request "Focus on the oauth-service package and razorpay integration."
   ```
   Equivalent Codex mention: `agent csa:security`

If you omit `--agent`, the CLI will choose the `default_agent` specified in the configuration file.
