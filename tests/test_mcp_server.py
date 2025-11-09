"""Tests for MCP server utilities."""

import asyncio
import types

import pytest

from codex_sub_agent.agent_runtime import AgentAliasEntry, AgentBlueprint
from codex_sub_agent.config_models import AgentSettings, MCPHttpConfig, MCPStdioConfig, OpenAISettings, SubAgentConfig
from codex_sub_agent.mcp_server import format_run_result, initialize_mcp_servers, run_agent_workflow


def _agent_settings() -> AgentSettings:
    return AgentSettings(
        name="Demo",
        model="gpt-5",
        instructions="Top line",
        default_prompt="Prompt",
        skills=[],
        mcp_servers=[],
    )


def test_format_run_result_handles_missing_output() -> None:
    blueprint = AgentBlueprint(agent_id="demo", settings=_agent_settings(), mcp_server_names=[])
    alias_entry = AgentAliasEntry(alias="demo", tool_name="demo", blueprint=blueprint, description="")

    class DummyResult:
        final_output = None
        last_agent = types.SimpleNamespace(name="Helper")

    text = format_run_result(alias_entry, DummyResult())
    assert "Helper" in text


def test_initialize_mcp_servers_starts_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict] = []

    class DummyServer:
        def __init__(self, params, name, client_session_timeout_seconds):
            created.append({"name": name, "params": params})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("HTTP_TOKEN", "token")
    monkeypatch.setattr("codex_sub_agent.mcp_server.MCPServerStdio", DummyServer)
    monkeypatch.setattr("codex_sub_agent.mcp_server.MCPServerStreamableHttp", DummyServer)

    config = SubAgentConfig(
        openai=OpenAISettings(),
        agents={"demo": _agent_settings()},
        aliases={"demo": "demo"},
        mcp_servers={
            "codex": MCPStdioConfig(type="stdio", name="Codex", command="echo"),
            "http": MCPHttpConfig(type="http", name="HTTP", url="https://example.com", bearer_token_env_var="HTTP_TOKEN"),
        },
    )

    servers, stack = asyncio.run(initialize_mcp_servers(config, ["codex", "http"]))
    assert set(servers) == {"codex", "http"}
    assert len(created) == 2
    asyncio.run(stack.aclose())


def test_run_agent_workflow_invokes_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    class DummyServer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setattr("codex_sub_agent.mcp_server.MCPServerStdio", lambda **_: DummyServer())
    monkeypatch.setattr("codex_sub_agent.mcp_server.MCPServerStreamableHttp", lambda **_: DummyServer())

    async def fake_run(agent, entry_message):
        calls.append((agent, entry_message))
        return "done"

    monkeypatch.setattr("codex_sub_agent.mcp_server.Runner.run", staticmethod(fake_run))

    settings = _agent_settings().model_copy(update={"mcp_servers": ["codex"]})
    config = SubAgentConfig(
        openai=OpenAISettings(),
        agents={"demo": settings},
        aliases={"demo": "demo"},
        mcp_servers={"codex": MCPStdioConfig(type="stdio", name="Codex", command="echo")},
    )

    blueprint = AgentBlueprint(agent_id="demo", settings=settings, mcp_server_names=["codex"])
    entry = AgentAliasEntry(alias="demo", tool_name="demo", blueprint=blueprint, description="")

    result = asyncio.run(run_agent_workflow(entry, config, requested_prompt="Override"))
    assert result == "done"
    assert calls and calls[0][1] == "Override"
