"""Integration-style tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path

import pytest

from codex_sub_agent import cli


def invoke_cli(config_path: Path, *args: str) -> int:
    """Invoke the CLI entry point with the provided arguments."""

    argv = ["--config", str(config_path), *args]
    return cli.main(argv)


def test_cli_lists_agents(sample_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The --list-agents flag should exit successfully."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    exit_code = invoke_cli(sample_config_dir / "codex_sub_agents.toml", "--list-agents")
    assert exit_code == 0


def test_cli_print_config(sample_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The --print-config flag should also exit successfully."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    exit_code = invoke_cli(sample_config_dir / "codex_sub_agents.toml", "--print-config")
    assert exit_code == 0


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
