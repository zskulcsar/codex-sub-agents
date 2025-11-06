"""Unit tests for the configuration loader utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_sub_agent.config_loader import InvalidConfiguration, load_config


def test_load_default_config_ships_agents() -> None:
    """The bundled default configuration should expose all sub-agents."""
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "codex_sub_agents.toml"
    config = load_config(config_path)

    assert config.default_agent_id == "workflow"
    assert sorted(config.available_agents().keys()) == [
        "security_review",
        "test_agent",
        "workflow",
    ]
    assert config.aliases["csa:test-agent"] == "test_agent"
    assert config.resolve_agent("csa:test-agent")[0] == "test_agent"


def test_resolve_agent_rejects_unknown_alias(tmp_path: Path) -> None:
    """resolve_agent should raise when an alias points to a missing agent."""
    config_file = tmp_path / "sample.toml"
    config_file.write_text(
        """
default_agent = "workflow"

[aliases]
"alias:missing" = "nonexistent"

[openai]
api_key_env_var = "OPENAI_API_KEY"
default_api = "responses"

[agents.workflow]
name = "Workflow"
model = "gpt-5"
instructions = "Do work"
entry_message = "Start"

[mcp_servers.codex]
type = "stdio"
name = "Codex"
command = "npx"
"""
    )

    config = load_config(config_file)
    with pytest.raises(InvalidConfiguration):
        config.resolve_agent("alias:missing")
