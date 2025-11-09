# Codex Sub-Agent

This package ships a reusable sub-agent that exposes Codex CLI as an MCP server and augments it with Context7 documentation search and GitHub automation. Install it into any Codex-enabled environment and register it in `.codex/config.toml` to enable the workflow.

## Installation

```bash
uv pip install --system .
# or: pip install .
```

## Configuration

Copy the configuration bundle from the project’s root `config/` directory to your preferred location (for example `~/.config/codex/`), then adjust paths as needed:

```bash
mkdir -p ~/.config/codex
cp -R config/* ~/.config/codex/
```

- `codex_sub_agents.toml` defines shared OpenAI settings, the `[aliases]` map, and any reusable MCP server definitions (Codex wrapper, GitHub, Context7, etc.). The `[mcp_servers.*]` section is optional—declare only the servers you plan to reference from agents.
- Each `agents/<name>/` directory contains `agent.toml`, `entry_message.md`, and `instructions.md`. The TOML file holds the structured fields (id, model, mcp_servers, etc.) while the Markdown files keep rich text for the entry message and long-form instructions.

Paths listed under `agent_files` are resolved relative to the main TOML file, so moving the folder together keeps references intact. Add or remove agent files by editing that list; each agent file must declare an `id` plus an `[agent]` table with the usual fields (instructions, entry_message, etc.).
When an agent lists a server in `mcp_servers`, the runtime verifies that an entry exists under `[mcp_servers.<name>]` before launching the workflow so typos are caught up front.

Expose stable mentions via the `[aliases]` table so Codex users can call agents by name:

```toml
[aliases]
"csa:default" = "workflow"
"csa:test-agent" = "test_agent"
"csa:security" = "security_review"
```

Inside Codex, run `agent csa:default`, `agent csa:test-agent`, or `agent csa:security` to dispatch the matching sub-agent without remembering internal IDs.

If you install the wheel from PyPI, the CLI automatically falls back to the packaged version of this bundle (resolved with `importlib.resources`) so `codex-sub-agent --list-agents` works out-of-the-box. Supplying `--config` still lets you point to a customized copy, like the example above.

> MCP tool names may only contain `[A-Za-z0-9_-]`, so when Codex lists tools it replaces punctuation in the alias (for example `csa:test-agent` → `csa_test-agent`). Use the sanitized name inside Codex (`agent csa_test-agent`), but the CLI always accepts the original alias (`--run-agent csa:test-agent`).

Once the configuration bundle is in place, register the MCP server automatically:

```bash
codex-sub-agent configure --config ~/.config/codex/codex_sub_agents.toml
```

The command updates (or creates) `./.codex/config.toml` in your current project and safely skips the insert if the stanza already exists. Override the target file with `--codex-config` if needed.

Set the following environment variables so the agent can authenticate:

- `OPENAI_API_KEY`
- `GITHUB_PERSONAL_ACCESS_TOKEN` (if you want access to the GitHub MCP server)

Install [direnv](https://direnv.net/) and run `direnv allow` in repositories that contain a `.envrc`. The CLI uses `direnv export json` to hydrate any missing secrets (e.g., `OPENAI_API_KEY`) so that only trusted directories can influence your environment.

## Registering with Codex CLI

If you prefer to make the change manually, add the following stanza to `.codex/config.toml`:

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
   codex-sub-agent --config ~/.config/codex/codex_sub_agents.toml --run-agent csa:test-agent
   ```
   You should see `Codex sub-agent configuration is correct. You can now use sub agents!`
   (Inside an interactive Codex session, invoke `agent csa_test-agent` — alias `csa:test-agent` — to trigger the same check.)
3. Run the default workflow agent (explicit):
   ```bash
   codex-sub-agent --config ~/.config/codex/codex_sub_agents.toml --run-agent workflow
   ```
   Equivalent Codex mention: `agent csa_default` (alias `csa:default`)
4. Run the security review agent with a custom kickoff request:
   ```bash
   codex-sub-agent \
     --config ~/.config/codex/codex_sub_agents.toml \
     --run-agent csa:security \
     --request "Focus on the oauth-service package and razorpay integration."
   ```
   Equivalent Codex mention: `agent csa_security` (alias `csa:security`)

If you omit `--run-agent`, the CLI starts the MCP server and exposes every configured agent as an MCP tool.

### TODO

* Update the code so that the agents can be configured with markdown files instead of toml. The files should live in separate folders under the `config` bundling the agent's description and configuration together.
