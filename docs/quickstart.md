# Quickstart

When you only have a few minutes, follow this page to get Codex Sub-Agent running end-to-end.

## 1. Check Prerequisites

- macOS, Linux, or WSL with Python 3.11+ and Node.js 18+ available on `PATH`.
- Access to `uv` or `pip` for installation.
- Environment variables ready: `OPENAI_API_KEY` (always) and `GITHUB_PERSONAL_ACCESS_TOKEN` if you plan to talk to GitHub.

## 2. Install the Package

```bash
uv pip install --system .
# OR
pip install .
```

The CLI entry point `codex-sub-agent` becomes available immediately after the install finishes.

## 3. Copy the Configuration Bundle

1. Pick a config home such as `~/.config/codex/`.
2. Copy the project’s `config/` directory into that location, keeping the folder structure intact (`codex_sub_agents.toml` plus `agents/*.toml`).

```bash
mkdir -p ~/.config/codex
cp -R config ~/.config/codex/
```

## 4. Register the MCP Server with Codex CLI

From the repository root run:

```bash
codex-sub-agent configure --config ~/.config/codex/codex_sub_agents.toml
```

This inserts the correct stanza into `./.codex/config.toml` (creating the file when missing).

## 5. Verify the Installation

1. List agents:
   ```bash
   codex-sub-agent --config ~/.config/codex/codex_sub_agents.toml --list-agents
   ```
2. Run the smoke-test agent:
   ```bash
   codex-sub-agent \
     --config ~/.config/codex/codex_sub_agents.toml \
     --run-agent csa:test-agent
   ```
   Expected output: `Codex sub-agent configuration is correct. You can now use sub agents!`

## 6. What’s Next

- Need more control over dependencies? See `installation.md`.
- Want to customize agents or MCP servers? Jump to `configuration.md`.
- Hit an error? Head straight to `troubleshooting.md`.
