# Installation & Upgrade Guide

This page expands on installation scenarios for teams that need repeatable, auditable steps.

## Supported Environments

| Component | Requirement |
| --- | --- |
| Python | >= 3.11 with `pip` or `uv` |
| Node.js | >= 18 (needed for Codex CLI / MCP helpers) |
| OpenAI access | `OPENAI_API_KEY` with Responses API enabled |
| Optional GitHub MCP | `GITHUB_PERSONAL_ACCESS_TOKEN` with `repo` + `workflow` scopes |

## Fresh Install

```bash
# Inside the repository clone
uv pip install --system .
# or
pip install .
```

- Installs the CLI (`codex-sub-agent`) and shared config bundle.
- Adds dependencies like `openai`, `openai-agents`, and `mcp`.

## Isolated Virtual Environment (Optional)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install .
```

Useful when you need to test multiple versions side-by-side.

## Development Extras

```bash
pip install .[dev]
```

Adds `pytest`, `ruff`, `mypy`, `pdoc`, and build tooling.

## Upgrading

```bash
pip install --upgrade codex-sub-agent
# For editable installs
pip install --upgrade .
```

After upgrading, rerun `codex-sub-agent --list-agents` to confirm the new CLI still reads your config.

## Uninstall / Reset

```bash
pip uninstall codex-sub-agent
rm -rf ~/.config/codex/config ~/.config/codex/agents
rm -rf ./.codex/config.toml  # optional reset inside each repo
```

If you reinstall later, repeat the Quickstart to copy fresh config files and re-register the MCP server.
