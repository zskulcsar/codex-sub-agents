"""Command-line entry point and MCP server implementation for Codex sub-agents."""

import argparse
import asyncio
import importlib.resources as importlib_resources
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from agents import set_default_openai_api, set_default_openai_key

from .agent_runtime import AgentRegistry
from .config_loader import InvalidConfiguration, SubAgentConfig, load_config
from . import mcp_server


def _default_config_path() -> Path | None:
    """Return the packaged configuration file shipped with the module."""

    try:
        resource = importlib_resources.files("codex_sub_agent_config") / "codex_sub_agents.toml"
    except ModuleNotFoundError:  # pragma: no cover - only during broken installs
        return None

    try:
        with importlib_resources.as_file(resource) as resolved:
            if resolved.exists():
                return resolved
    except FileNotFoundError:
        return None
    return None


def build_main_parser() -> argparse.ArgumentParser:
    """Construct the primary CLI parser for launching the MCP server.

    Returns:
        Configured `argparse.ArgumentParser` for standard operations.
    """
    parser = argparse.ArgumentParser(
        prog="codex-sub-agent",
        description="Expose configured Codex workflows as an MCP server.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to codex_sub_agents.toml (defaults to the packaged config).",
    )
    parser.add_argument(
        "--run-agent",
        dest="run_agent",
        type=str,
        help="Execute a specific agent (by alias or agent id) locally and exit.",
    )
    parser.add_argument(
        "--request",
        type=str,
        default=None,
        help="Override the entry message when using --run-agent.",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="Print the configured agents and aliases, then exit.",
    )
    return parser


def build_configure_parser() -> argparse.ArgumentParser:
    """Construct the `configure` sub-command parser.

    Returns:
        Parser pre-populated with the `configure` command options.
    """
    parser = argparse.ArgumentParser(
        prog="codex-sub-agent configure",
        description="Add the codex-sub-agent MCP stanza to ./.codex/config.toml.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to codex_sub_agents.toml that Codex should reference.",
    )
    parser.add_argument(
        "--codex-config",
        type=Path,
        default=Path.cwd() / ".codex" / "config.toml",
        help="Path to the Codex config file (default: ./.codex/config.toml).",
    )
    return parser






def _load_env_from_direnv(directory: Path) -> dict[str, str]:
    """Execute `direnv export json` within ``directory`` and return the environment."""

    if shutil.which("direnv") is None:
        raise RuntimeError("direnv executable not found in PATH.")

    command = ["direnv", "export", "json"]
    result = subprocess.run(command, cwd=str(directory), capture_output=True, text=True)
    if result.returncode != 0:
        error_output = result.stderr.strip() or "direnv export failed"
        raise RuntimeError(error_output)

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("direnv export produced invalid JSON output.") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("direnv export response must be a JSON object.")

    env_map: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            env_map[key] = value
    return env_map


def _populate_env_from_envrc(config: SubAgentConfig) -> None:
    """Ensure required env vars are populated via direnv when available."""

    required: list[str] = []
    if config.openai.api_key_env_var:
        required.append(config.openai.api_key_env_var)

    missing = [var for var in required if var and not os.environ.get(var)]
    if not missing:
        return

    envrc_path = Path.cwd() / ".envrc"
    if not envrc_path.exists():
        return

    try:
        env_map = _load_env_from_direnv(envrc_path.parent)
    except RuntimeError:
        return

    # TODO: this works, but ideally we want to re-source all the variables from .envrc for the sub-agents
    for var in missing:
        value = env_map.get(var)
        if value:
            os.environ[var] = value


def ensure_openai_setup(config: SubAgentConfig) -> None:
    """Validate and configure shared OpenAI credentials for the Agents SDK.

    Args:
        config: Global configuration describing key names and defaults.

    Raises:
        RuntimeError: If the required API key environment variable is missing.
    """
    api_key = os.environ.get(config.openai.api_key_env_var)
    if not api_key:
        raise RuntimeError(
            f"Missing environment variable {config.openai.api_key_env_var}. "
            "Set it before launching codex-sub-agent."
        )
    set_default_openai_key(api_key)
    set_default_openai_api(config.openai.default_api)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for launching the MCP server or helper commands.

    Args:
        argv: Optional argument override primarily used for testing.

    Returns:
        Process exit code (0 for success, non-zero for errors).
    """
    argv = argv or sys.argv[1:]

    if argv and argv[0] == "configure":
        config_parser = build_configure_parser()
        args = config_parser.parse_args(argv[1:])
        return configure_codex(args.config, args.codex_config)

    parser = build_main_parser()
    args = parser.parse_args(argv)

    if args.config is None:
        parser.error(
            "No configuration file supplied. Pass --config with the path to codex_sub_agents.toml."
        )

    config_path = args.config.expanduser()
    if not config_path.exists():
        parser.error(f"Configuration file not found: {config_path}")

    try:
        config = load_config(config_path)
        _populate_env_from_envrc(config)
        registry = AgentRegistry(config)
    except InvalidConfiguration as exc:
        parser.error(str(exc))

    if args.list_agents:
        for agent_id, settings, aliases in registry.iter_agent_summaries():
            alias_render: list[str] = []
            for alias in aliases:
                entry = registry.cli_aliases.get(alias)
                if entry and entry.expose_in_tools:
                    alias_render.append(f"{alias} (tool {entry.tool_name})")
                else:
                    alias_render.append(alias)
            alias_text = f" aliases={alias_render}" if alias_render else ""
            print(f"{agent_id}: {settings.name}{alias_text}")
        return 0

    if args.run_agent:
        try:
            entry = registry.resolve_cli_alias(args.run_agent)
        except InvalidConfiguration as exc:
            parser.error(str(exc))
        ensure_openai_setup(config)
        try:
            run_result = asyncio.run(mcp_server.run_agent_workflow(entry, config, args.request))
            print(mcp_server.format_run_result(entry, run_result))
            return 0
        except Exception as exc:  # pragma: no cover - CLI surface
            print(f"codex-sub-agent failed: {exc}", file=sys.stderr)
            return 1

    ensure_openai_setup(config)
    try:
        asyncio.run(mcp_server.serve(config, registry))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # pragma: no cover - MCP surface
        print(f"codex-sub-agent failed: {exc}", file=sys.stderr)
        return 1


def configure_codex(config_path: Path, codex_config_path: Path) -> int:
    """Write the codex-sub-agent stanza into ./.codex/config.toml.

    Args:
        config_path: Path to the codex_sub_agents.toml configuration.
        codex_config_path: Target Codex configuration file to update.

    Returns:
        Integer exit status suitable for CLI usage.
    """
    config_path = config_path.expanduser().resolve()
    if not config_path.exists():
        print(f"Configuration file not found: {config_path}", file=sys.stderr)
        return 1

    codex_config_path = codex_config_path.expanduser()
    codex_config_path.parent.mkdir(parents=True, exist_ok=True)

    stanza_header = "[mcp_servers.codex_sub_agent]"
    stanza = (
        f"{stanza_header}\n"
        'command = "codex-sub-agent"\n'
        f'args = ["--config", "{config_path}"]\n'
        "startup_timeout_sec = 60\n"
        "client_session_timeout_seconds = 3600\n"
    )

    if codex_config_path.exists():
        existing_text = codex_config_path.read_text()
        if stanza_header in existing_text:
            print(f"{codex_config_path} already contains the codex_sub_agent stanza.")
            return 0
        newline = "" if existing_text.endswith("\n") else "\n"
        codex_config_path.write_text(existing_text + newline + "\n" + stanza)
    else:
        codex_config_path.write_text(stanza)

    print(f"Added codex_sub_agent MCP server configuration to {codex_config_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
