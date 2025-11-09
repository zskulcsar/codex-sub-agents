"""Unit tests for the agent_runtime helpers."""

from codex_sub_agent.agent_runtime import AgentRegistry
from codex_sub_agent.config_models import AgentSettings, MCPStdioConfig, OpenAISettings, SubAgentConfig


def _make_config() -> SubAgentConfig:
    agent = AgentSettings(
        name="Demo Agent",
        model="gpt-5",
        instructions="Primary instruction line.\nSecond line.",
        default_prompt="Kick things off.",
        mcp_servers=["codex"],
        skills=[],
    )

    return SubAgentConfig(
        openai=OpenAISettings(),
        agents={"demo": agent},
        aliases={"csa:demo": "demo"},
        mcp_servers={"codex": MCPStdioConfig(type="stdio", name="Codex", command="echo")},
    )


def test_agent_registry_exposes_tool_metadata() -> None:
    """Registry should sanitize alias names into valid tool identifiers."""

    registry = AgentRegistry(_make_config())

    entry = registry.resolve_cli_alias("csa:demo")
    assert entry.alias == "csa:demo"
    assert entry.tool_name.startswith("csa_demo")
    assert registry.tool_definitions[0].name == entry.tool_name
    summary = registry.tool_definitions[0].description
    assert "Demo Agent" in summary


def test_agent_registry_lists_summaries() -> None:
    """iter_agent_summaries should return deterministic tuples."""

    registry = AgentRegistry(_make_config())
    summaries = list(registry.iter_agent_summaries())
    assert len(summaries) == 1
    agent_id, settings, aliases = summaries[0]
    assert agent_id == "demo"
    assert settings.name == "Demo Agent"
    assert aliases == ["csa:demo"]
