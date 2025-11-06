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
