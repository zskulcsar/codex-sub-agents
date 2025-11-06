"""Command-line entry point for the Codex sub-agent orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Dict

from agents import Agent, ModelSettings, Runner, set_default_openai_api, set_default_openai_key
from agents.mcp import MCPServer, MCPServerStdio, MCPServerStdioParams, MCPServerStreamableHttp, MCPServerStreamableHttpParams

from .config_loader import AgentSettings, InvalidConfiguration, MCPHttpConfig, MCPStdioConfig, SubAgentConfig, load_config


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser with all supported flags."""

    parser = argparse.ArgumentParser(
        prog="codex-sub-agent",
        description="Launch the Codex CLI sub-agent described in the configuration file.",
    )
    default_config = (
        Path(__file__).resolve().parent.parent / "config" / "codex_sub_agents.toml"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config if default_config.exists() else None,
        help="Path to the TOML configuration file describing the agent task.",
    )
    parser.add_argument(
        "--request",
        type=str,
        default=None,
        help="Override the entry message defined in the configuration file.",
    )
    parser.add_argument(
        "--agent",
        dest="agent_id",
        type=str,
        default=None,
        help="Identifier of the sub-agent to run (as defined in the configuration file).",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List all available agent identifiers in the configuration and exit.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the resolved configuration and exit.",
    )
    return parser


async def initialize_mcp_servers(config: SubAgentConfig) -> tuple[Dict[str, MCPServer], AsyncExitStack]:
    """Start all configured MCP servers and return them alongside an exit stack.

    Args:
        config: Hydrated configuration describing the desired MCP servers.

    Returns:
        A tuple containing a mapping of server names to active MCP server instances
        and the :class:`AsyncExitStack` responsible for shutting them down.

    Raises:
        RuntimeError: If required environment variables for an MCP server are missing.
    """

    servers: Dict[str, MCPServer] = {}
    exit_stack = AsyncExitStack()
    await exit_stack.__aenter__()

    for name, server_config in config.mcp_servers.items():
        server: MCPServer
        if isinstance(server_config, MCPStdioConfig):
            stdio_params: MCPServerStdioParams = {"command": server_config.command}
            if server_config.args:
                stdio_params["args"] = server_config.args
            if server_config.env:
                stdio_params["env"] = server_config.env

            server = MCPServerStdio(
                params=stdio_params,
                name=server_config.name,
                client_session_timeout_seconds=server_config.client_session_timeout_seconds,
            )
        elif isinstance(server_config, MCPHttpConfig):
            headers = dict(server_config.headers)
            if server_config.bearer_token_env_var:
                token = os.environ.get(server_config.bearer_token_env_var)
                if not token:
                    raise RuntimeError(
                        f"Environment variable {server_config.bearer_token_env_var} must be set "
                        f"to start MCP server '{name}'."
                    )
                headers.setdefault("Authorization", f"Bearer {token}")

            http_params: MCPServerStreamableHttpParams = {"url": server_config.url}
            if headers:
                http_params["headers"] = headers

            server = MCPServerStreamableHttp(
                params=http_params,
                name=server_config.name,
                client_session_timeout_seconds=server_config.client_session_timeout_seconds,
            )
        else:  # pragma: no cover - defensive
            raise RuntimeError(f"Unsupported MCP server type for {name}")

        servers[name] = await exit_stack.enter_async_context(server)

    return servers, exit_stack


async def run_agent(
    config: SubAgentConfig,
    agent_settings: AgentSettings,
    agent_id: str,
    request: str | None,
    display_label: str,
) -> None:
    """Run a single sub-agent workflow to completion.

    Args:
        config: Shared configuration containing OpenAI credentials and MCP servers.
        agent_settings: Specific agent configuration (instructions, model settings).
        agent_id: Canonical identifier for the agent being run.
        request: Optional override for the agent's entry message.
        display_label: Identifier or alias used to launch the agent (for logging).

    Raises:
        RuntimeError: If required environment variables such as ``OPENAI_API_KEY`` are
            missing.
    """

    api_key = os.environ.get(config.openai.api_key_env_var)
    if not api_key:
        raise RuntimeError(
            f"Missing environment variable {config.openai.api_key_env_var}. "
            "Set it before launching the sub-agent."
        )

    set_default_openai_key(api_key)
    set_default_openai_api(config.openai.default_api)

    servers, exit_stack = await initialize_mcp_servers(config)
    try:
        model_settings = ModelSettings()
        if agent_settings.temperature is not None:
            model_settings.temperature = agent_settings.temperature
        if agent_settings.reasoning_tokens:
            model_settings.max_tokens = agent_settings.reasoning_tokens

        agent = Agent(
            name=agent_settings.name,
            instructions=agent_settings.instructions,
            model=agent_settings.model,
            mcp_servers=list(servers.values()),
            model_settings=model_settings,
        )

        entry = request or agent_settings.entry_message
        result = await Runner.run(agent, entry)
        last_agent = result.last_agent.name if result.last_agent else agent_settings.name
        suffix = f" (alias: {display_label})" if display_label != agent_id else ""
        print(
            f"[codex-sub-agent] Agent '{agent_id}'{suffix} run completed. Last agent: {last_agent}"
        )
    finally:
        await exit_stack.aclose()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point compatible with ``python -m codex_sub_agent.cli``."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        if args.config is None:
            parser.error(
                "No configuration file supplied. Pass --config with the path to "
                "codex_sub_agents.toml."
            )
        if not args.config.exists():
            parser.error(f"Configuration file not found: {args.config}")

        config = load_config(args.config)
    except InvalidConfiguration as exc:
        parser.error(str(exc))

    if args.print_config:
        print(config.model_dump_json(indent=2))
        return 0

    if args.list_agents:
        try:
            agents = config.available_agents()
        except InvalidConfiguration as exc:
            parser.error(str(exc))
        alias_index: Dict[str, list[str]] = {}
        for alias, target in config.aliases.items():
            alias_index.setdefault(target, []).append(alias)
        for key, value in sorted(agents.items()):
            aliases = ", ".join(sorted(alias_index.get(key, [])))
            if aliases:
                print(f"{key}: {value.name} (model={value.model}) aliases=[{aliases}]")
            else:
                print(f"{key}: {value.name} (model={value.model})")
        return 0

    try:
        resolved_agent_id, agent_settings = config.resolve_agent(args.agent_id)
    except InvalidConfiguration as exc:
        parser.error(str(exc))

    try:
        display_label = args.agent_id or resolved_agent_id
        asyncio.run(run_agent(config, agent_settings, resolved_agent_id, args.request, display_label))
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"codex-sub-agent failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
