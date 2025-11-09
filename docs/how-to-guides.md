# How-To Guides

Pick the scenario closest to your task and follow the numbered steps.

## Add a New Agent Profile

1. Copy an existing folder under `config/agents/` (for example `workflow/`) and rename it.
2. Edit the new folder’s `agent.toml` (`id`, `name`, `model`, `mcp_servers`, tokens/temperature).
3. Update `instructions.md` and `default_prompt.md` with Markdown content.
4. Add an alias in `codex_sub_agents.toml`:
   ```toml
   [aliases]
   "csa:research" = "research_agent"
   ```
5. Re-run `codex-sub-agent --list-agents` to confirm the alias and tool name. Skills inside the new folder are parsed by `codex_sub_agent.skill_loader` and exposed as tools via `codex_sub_agent.skills`, so no extra wiring is required.

## Rotate GitHub Credentials

1. Create a fresh PAT with `repo`, `workflow`, and `read:org` scopes.
2. Update your shell config:
   ```bash
   export GITHUB_PERSONAL_ACCESS_TOKEN=<new token>
   ```
3. Restart shells or CI jobs so the new token propagates.
4. Rerun any workflow that touches GitHub to verify access.

## Point the CLI at a Custom Config Path

```bash
codex-sub-agent --config /path/to/codex_sub_agents.toml --list-agents
```

Use this when you maintain multiple bundles (e.g., staging vs. production).

## Run a Workflow Non-Interactively

```bash
codex-sub-agent \
  --config ~/.config/codex/codex_sub_agents.toml \
  --run-agent workflow \
  --request "Summarize open tasks in README"
```

Capture stdout/stderr to logs when running inside CI.

## Reinstall the Config Bundle

1. Delete the existing folder: `rm -rf ~/.config/codex/config ~/.config/codex/agents`.
2. Copy the latest bundle from the repo.
3. Rerun `codex-sub-agent configure --config <new path>` to ensure Codex CLI points to the updated files.

## Running Tests

- Full suite: `pytest`
- Targeted helpers:
  - `pytest tests/test_agent_runtime.py` (alias registry + blueprints)
  - `pytest tests/test_config_models_unit.py` (Pydantic models/validation)
  - `pytest tests/test_skill_loader.py tests/test_skills.py` (skill manifests + tool rendering)
  - `pytest tests/test_mcp_server.py` (MCP orchestration, `run_agent_workflow`, and server initialization)
