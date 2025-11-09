"""Tests for loading agent configurations from multi-file directories."""

from pathlib import Path

from codex_sub_agent.config_loader import load_config


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_config_supports_agent_directory(tmp_path: Path) -> None:
    """Agent directories split into TOML + Markdown are parsed into AgentSettings."""

    config_root = tmp_path / "config"
    agent_dir = config_root / "agents" / "demo"

    _write_file(
        agent_dir / "agent.toml",
        """
        id = "demo"

        [agent]
        name = "Demo Agent"
        model = "gpt-5"
        reasoning_tokens = 2048
        mcp_servers = ["codex"]
        """,
    )
    _write_file(agent_dir / "instructions.md", "Use the Codex MCP server.")
    _write_file(agent_dir / "entry_message.md", "Kick things off.")

    _write_file(
        config_root / "codex_sub_agents.toml",
        """
        agent_files = ["agents/demo"]

        [openai]
        api_key_env_var = "OPENAI_API_KEY"
        default_api = "responses"

        [mcp_servers.codex]
        type = "stdio"
        name = "Codex CLI"
        command = "npx"
        args = ["-y", "codex", "mcp-server"]
        client_session_timeout_seconds = 60
        """,
    )

    config = load_config(config_root / "codex_sub_agents.toml")
    agent = config.available_agents()["demo"]

    assert agent.name == "Demo Agent"
    assert agent.instructions == "Use the Codex MCP server."
    assert agent.entry_message == "Kick things off."
