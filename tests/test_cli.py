"""Integration-style tests for the CLI entry point."""

from pathlib import Path
import os

from agents.tool import FunctionTool

import pytest

from codex_sub_agent import cli
from codex_sub_agent.config_loader import load_config


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _configure_agent_with_skill(tmp_path: Path) -> tuple[Path, cli.AgentBlueprint]:
    config_root = tmp_path / "config"
    agent_dir = config_root / "agents" / "demo"
    skill_dir = agent_dir / "skills" / "deep_focus"

    _write(
        agent_dir / "agent.toml",
        """
id = "demo"

[agent]
name = "Demo Agent"
mcp_servers = ["codex"]
""",
    )
    _write(agent_dir / "instructions.md", "Primary instructions.")
    _write(agent_dir / "default_prompt.md", "Kick things off.")
    _write(
        skill_dir / "SKILL.md",
        """---
name: Deep Focus
description: Stay on the main objective.
---
Always brainstorm before coding and confirm the plan with the user.
""",
    )
    _write(skill_dir / "large_skill_file.md", "Long-form guidance.")

    config_path = config_root / "codex_sub_agents.toml"
    _write(
        config_path,
        """
agent_files = ["agents/demo"]

[mcp_servers.codex]
type = "stdio"
name = "Codex CLI"
command = "npx"
client_session_timeout_seconds = 60
""",
    )

    config = load_config(config_path)
    settings = config.available_agents()["demo"]
    blueprint = cli.AgentBlueprint(agent_id="demo", settings=settings, mcp_server_names=[])
    return config_path, blueprint


def test_cli_lists_agents(sample_config_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The --list-agents flag should enumerate configured aliases."""

    exit_code = cli.main(["--config", str(sample_config_dir / "codex_sub_agents.toml"), "--list-agents"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "workflow" in output
    assert "csa:test-agent" in output
    assert "tool csa_test-agent" in output


def test_configure_adds_stanza(sample_config_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """configure should append the stanza when it is missing."""

    codex_config = tmp_path / ".codex" / "config.toml"
    exit_code = cli.main(
        [
            "configure",
            "--config",
            str(sample_config_dir / "codex_sub_agents.toml"),
            "--codex-config",
            str(codex_config),
        ]
    )
    assert exit_code == 0

    content = codex_config.read_text()
    assert "[mcp_servers.codex_sub_agent]" in content
    assert str((sample_config_dir / "codex_sub_agents.toml").resolve()) in content
    captured = capsys.readouterr()
    assert "Added codex_sub_agent" in captured.out


def test_configure_is_idempotent(sample_config_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Running configure twice should report that the stanza already exists."""

    codex_config = tmp_path / ".codex" / "config.toml"
    args = [
        "configure",
        "--config",
        str(sample_config_dir / "codex_sub_agents.toml"),
        "--codex-config",
        str(codex_config),
    ]
    cli.main(args)  # first call adds stanza
    capsys.readouterr()  # flush output from first invocation
    first_content = codex_config.read_text()

    exit_code = cli.main(args)
    assert exit_code == 0
    second_content = codex_config.read_text()
    assert first_content == second_content

    captured = capsys.readouterr()
    assert "already contains the codex_sub_agent stanza" in captured.out


def test_run_agent_flag_invokes_alias(sample_config_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """--run-agent executes a single agent using the shared workflow helper."""

    async def fake_run_agent(alias_entry, config, request):
        class DummyResult:
            final_output = f"{alias_entry.alias}|{request or 'default'}"
            last_agent = None

        return DummyResult()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(cli, "run_agent_workflow", fake_run_agent)

    exit_code = cli.main(
        [
            "--config",
            str(sample_config_dir / "codex_sub_agents.toml"),
            "--run-agent",
            "csa:test-agent",
            "--request",
            "Focus on docs",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "csa:test-agent|Focus on docs" in output


def test_envrc_in_current_directory_supplies_missing_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When OPENAI_API_KEY is missing, direnv-provided values fill it in."""

    envrc = tmp_path / ".envrc"
    envrc.write_text('export OPENAI_API_KEY="from-envrc"\n', encoding="utf-8")
    config_path = tmp_path / "config" / "codex_sub_agents.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
agent_files = []

[mcp_servers.codex]
type = "stdio"
name = "Codex CLI"
command = "npx"
client_session_timeout_seconds = 60
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "_load_env_from_direnv", lambda _: {"OPENAI_API_KEY": "from-envrc"})

    cli._populate_env_from_envrc(load_config(config_path))
    assert os.environ["OPENAI_API_KEY"] == "from-envrc"


def test_envrc_does_not_override_existing_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If OPENAI_API_KEY is already set, .envrc is ignored."""

    envrc = tmp_path / ".envrc"
    envrc.write_text('export OPENAI_API_KEY="from-envrc"\n', encoding="utf-8")
    config_path = tmp_path / "config" / "codex_sub_agents.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        """
agent_files = []

[mcp_servers.codex]
type = "stdio"
name = "Codex CLI"
command = "npx"
client_session_timeout_seconds = 60
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "preexisting")
    monkeypatch.setattr(cli, "_load_env_from_direnv", lambda _: {"OPENAI_API_KEY": "from-envrc"})

    cli._populate_env_from_envrc(load_config(config_path))
    assert os.environ["OPENAI_API_KEY"] == "preexisting"


def test_agent_blueprint_builds_skill_tools(tmp_path: Path) -> None:
    """Skill metadata results in registered function tools on the agent."""

    _, blueprint = _configure_agent_with_skill(tmp_path)
    agent = blueprint.build_agent(mcp_servers=[])

    assert agent.tools, "Skill tool should be registered"
    tool = agent.tools[0]
    assert isinstance(tool, FunctionTool)
    assert tool.name.startswith("skill_deep_focus")
    assert "Deep Focus" in tool.description
