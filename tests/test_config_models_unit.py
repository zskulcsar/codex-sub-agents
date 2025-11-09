"""Unit tests for config_models module."""

import pytest

from codex_sub_agent.config_models import (
    AgentSettings,
    InvalidConfiguration,
    MCPStdioConfig,
    OpenAISettings,
    SubAgentConfig,
)


def _base_agent() -> AgentSettings:
    return AgentSettings(
        name="Demo",
        instructions="Instruction",
        default_prompt="Prompt",
        mcp_servers=["codex"],
        skills=[],
    )


def test_sub_agent_config_resolves_aliases() -> None:
    config = SubAgentConfig(
        openai=OpenAISettings(),
        agents={"demo": _base_agent()},
        aliases={"workflow": "demo"},
        default_agent_id=None,
        mcp_servers={"codex": MCPStdioConfig(type="stdio", name="Codex", command="echo")},
    )

    agent_id, settings = config.resolve_agent("workflow")
    assert agent_id == "demo"
    assert settings.default_prompt == "Prompt"


def test_available_agents_requires_entries() -> None:
    config = SubAgentConfig(
        openai=OpenAISettings(),
        agents={},
        aliases={},
        mcp_servers={"codex": MCPStdioConfig(type="stdio", name="Codex", command="echo")},
    )

    with pytest.raises(InvalidConfiguration):
        config.available_agents()
