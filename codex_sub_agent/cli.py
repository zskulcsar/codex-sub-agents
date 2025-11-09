"""Command-line entry point and MCP server implementation for Codex sub-agents."""

import argparse
import asyncio
import importlib.resources as importlib_resources
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from agents import Agent, ModelSettings, RunResult, Runner, set_default_openai_api, set_default_openai_key
from agents.mcp import (
    MCPServer,
    MCPServerStdio,
    MCPServerStdioParams,
    MCPServerStreamableHttp,
    MCPServerStreamableHttpParams,
)
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as mcp_types

from . import __version__
from .config_loader import AgentSettings, InvalidConfiguration, MCPHttpConfig, MCPStdioConfig, SubAgentConfig, load_config

AGENT_TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "request": {
            "type": "string",
            "description": "Optional override for the agent's entry message.",
        },
    },
    "additionalProperties": False,
}


@dataclass(frozen=True)
class AgentBlueprint:
    """Immutable recipe for constructing an Agents SDK Agent."""

    agent_id: str
    settings: AgentSettings
    mcp_server_names: list[str]

    def build_agent(self, mcp_servers: Iterable[MCPServer]) -> Agent[Any]:
        """Create an Agents SDK `Agent` from the stored blueprint.

        Args:
            mcp_servers: Sequence of MCP server instances that should be exposed to
                the agent run.

        Returns:
            Fully configured `Agent` ready to be executed with `Runner`.
        """
        model_settings = ModelSettings()
        if self.settings.temperature is not None:
            model_settings.temperature = self.settings.temperature
        if self.settings.reasoning_tokens:
            model_settings.max_tokens = self.settings.reasoning_tokens

        return Agent(
            name=self.settings.name,
            instructions=self.settings.instructions,
            model=self.settings.model,
            model_settings=model_settings,
            mcp_servers=list(mcp_servers),
        )


@dataclass(frozen=True)
class AgentAliasEntry:
    alias: str
    tool_name: str
    blueprint: AgentBlueprint
    description: str
    expose_in_tools: bool = True


class AgentRegistry:
    """Holds the configured agents and exposes aliases for MCP tools and CLI use."""

    def __init__(self, config: SubAgentConfig):
        self.config = config
        agents = config.available_agents()
        self._blueprints: dict[str, AgentBlueprint] = {
            agent_id: AgentBlueprint(
                agent_id=agent_id,
                settings=settings,
                mcp_server_names=list(settings.mcp_servers),
            )
            for agent_id, settings in agents.items()
        }

        if not config.aliases:
            raise InvalidConfiguration("No aliases defined in [aliases]. At least one alias is required.")

        self.tool_entries: dict[str, AgentAliasEntry] = {}
        self.aliases_by_agent: dict[str, list[str]] = {agent_id: [] for agent_id in agents}
        used_tool_names: set[str] = set()

        for alias, agent_id in config.aliases.items():
            blueprint = self._blueprints.get(agent_id)
            if blueprint is None:
                raise InvalidConfiguration(f"Alias '{alias}' references unknown agent '{agent_id}'.")
            tool_name = self._make_tool_name(alias, used_tool_names)
            used_tool_names.add(tool_name)
            entry = AgentAliasEntry(
                alias=alias,
                tool_name=tool_name,
                blueprint=blueprint,
                description=self._summarize_agent(blueprint),
                expose_in_tools=True,
            )
            self.tool_entries[tool_name] = entry
            self.aliases_by_agent[agent_id].append(alias)

        self.cli_aliases: dict[str, AgentAliasEntry] = {}
        for entry in self.tool_entries.values():
            self.cli_aliases[entry.alias] = entry
            self.cli_aliases[entry.tool_name] = entry

        for agent_id, blueprint in self._blueprints.items():
            if agent_id not in self.cli_aliases:
                fallback_tool = self._make_tool_name(agent_id, used_tool_names)
                entry = AgentAliasEntry(
                    alias=agent_id,
                    tool_name=fallback_tool,
                    blueprint=blueprint,
                    description=self._summarize_agent(blueprint),
                    expose_in_tools=False,
                )
                self.cli_aliases[agent_id] = entry
                self.cli_aliases[fallback_tool] = entry

        self.tool_definitions: list[mcp_types.Tool] = [
            mcp_types.Tool(
                name=entry.tool_name,
                description=entry.description,
                inputSchema=AGENT_TOOL_INPUT_SCHEMA,
            )
            for entry in sorted(self.tool_entries.values(), key=lambda e: e.tool_name)
        ]

    def resolve_tool_name(self, tool_name: str) -> AgentAliasEntry:
        """Return the agent alias entry for a registered MCP tool name.

        Args:
            tool_name: Canonical MCP tool identifier returned by `list_tools`.

        Returns:
            The alias metadata associated with the requested tool.

        Raises:
            InvalidConfiguration: If the tool name is unknown.
        """
        if tool_name not in self.tool_entries:
            raise InvalidConfiguration(f"Unknown tool '{tool_name}'.")
        return self.tool_entries[tool_name]

    def resolve_cli_alias(self, alias: str) -> AgentAliasEntry:
        """Resolve CLI arguments (alias or tool name) to an agent entry.

        Args:
            alias: Name supplied by a user via CLI flags.

        Returns:
            Matching alias entry describing how to run the agent.

        Raises:
            InvalidConfiguration: If the alias is not configured.
        """
        if alias not in self.cli_aliases:
            raise InvalidConfiguration(f"Unknown agent '{alias}'. Available: {', '.join(sorted(self.cli_aliases))}")
        return self.cli_aliases[alias]

    def iter_agent_summaries(self) -> Iterable[tuple[str, AgentSettings, list[str]]]:
        """Yield configured agents with their CLI-visible aliases.

        Returns:
            Tuples of (agent_id, settings, aliases) for deterministic presentation.
        """
        for agent_id, blueprint in sorted(self._blueprints.items()):
            yield agent_id, blueprint.settings, sorted(self.aliases_by_agent.get(agent_id, []))

    @staticmethod
    def _summarize_agent(blueprint: AgentBlueprint) -> str:
        """Return a condensed description for displaying tool metadata.

        Args:
            blueprint: Agent blueprint whose instructions should be summarized.

        Returns:
            Single-line summary safe for CLI or MCP tool descriptions.
        """
        primary_line = blueprint.settings.instructions.strip().splitlines()[0].strip()
        if len(primary_line) > 200:
            primary_line = primary_line[:197].rstrip() + "..."
        return f"{blueprint.settings.name}: {primary_line}"

    @staticmethod
    def _make_tool_name(alias: str, used: set[str]) -> str:
        """Generate a sanitized, unique MCP tool name for an alias.

        Args:
            alias: Human-readable alias that needs to become an MCP tool name.
            used: Existing tool names that must be avoided.

        Returns:
            Sanitized tool name composed of safe characters.

        Raises:
            InvalidConfiguration: If a compliant tool name cannot be derived.
        """
        sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", alias)
        sanitized = sanitized.strip("_") or "agent"
        candidate = sanitized
        index = 2
        while candidate in used:
            candidate = f"{sanitized}_{index}"
            index += 1
        if not re.fullmatch(r"[A-Za-z0-9_-]+", candidate):
            raise InvalidConfiguration(f"Cannot derive a valid tool name from alias '{alias}'.")
        return candidate


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


async def initialize_mcp_servers(
    config: SubAgentConfig,
    server_names: Iterable[str],
) -> tuple[dict[str, MCPServer], AsyncExitStack]:
    """Start the MCP servers referenced by an agent blueprint.

    Args:
        config: Fully validated configuration with server definitions.
        server_names: Names requested by the agent blueprint (duplicates are ignored).

    Returns:
        Tuple of (active servers map, exit stack) that must remain open.

    Raises:
        InvalidConfiguration: If an agent references an unknown server.
        RuntimeError: If an HTTP server is missing a required credential.
    """
    servers: dict[str, MCPServer] = {}
    exit_stack = AsyncExitStack()
    await exit_stack.__aenter__()

    unique_names = list(dict.fromkeys(server_names))

    for name in unique_names:
        server_config = config.mcp_servers.get(name)
        if server_config is None:
            await exit_stack.aclose()
            raise InvalidConfiguration(f"Agent references unknown MCP server '{name}'.")
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

            stream_params: MCPServerStreamableHttpParams = {"url": server_config.url}
            if headers:
                stream_params["headers"] = headers

            server = MCPServerStreamableHttp(
                params=stream_params,
                name=server_config.name,
                client_session_timeout_seconds=server_config.client_session_timeout_seconds,
            )
        else:  # pragma: no cover
            raise RuntimeError(f"Unsupported MCP server type for {name}")

        servers[name] = await exit_stack.enter_async_context(server)

    return servers, exit_stack


async def run_agent_workflow(
    alias_entry: AgentAliasEntry,
    config: SubAgentConfig,
    requested_prompt: str | None,
) -> RunResult:
    """Execute an agent locally and capture the runner result.

    Args:
        alias_entry: Agent metadata specifying model settings and MCP servers.
        config: Root configuration containing MCP server definitions.
        requested_prompt: Optional entry message override supplied by the user.

    Returns:
        Runner result emitted by the Agents SDK execution pipeline.
    """
    servers, exit_stack = await initialize_mcp_servers(config, alias_entry.blueprint.mcp_server_names)
    try:
        agent = alias_entry.blueprint.build_agent(list(servers.values()))
        entry = requested_prompt or alias_entry.blueprint.settings.entry_message
        return await Runner.run(agent, entry)
    finally:
        await exit_stack.aclose()


def format_run_result(alias_entry: AgentAliasEntry, result: RunResult) -> str:
    """Render a `RunResult` into user-facing CLI text.

    Args:
        alias_entry: Agent metadata used when falling back to alias info.
        result: Execution outcome captured from the Agents SDK.

    Returns:
        Display-ready text summarizing the agent's final output.
    """
    final_output = getattr(result, "final_output", None)
    if isinstance(final_output, str) and final_output.strip():
        return final_output
    if final_output:
        try:
            return json.dumps(final_output, indent=2, default=str)
        except Exception:  # pragma: no cover - best effort
            return str(final_output)

    last_agent = getattr(result, "last_agent", None)
    last_agent_name = last_agent.name if last_agent else alias_entry.blueprint.settings.name
    return f"Agent '{alias_entry.alias}' completed via {last_agent_name}, but no final output was produced."


async def serve(config: SubAgentConfig, registry: AgentRegistry) -> int:
    """Expose configured agents as MCP tools over stdio.

    Args:
        config: Validated configuration used for runtime settings.
        registry: Registry providing alias resolution and tool definitions.

    Returns:
        Exit status compatible with CLI conventions.
    """
    server = Server(
        "codex-sub-agent",
        version=__version__,
        instructions="Codex sub-agent server that exposes configured workflows as MCP tools.",
    )
    tool_lock = asyncio.Lock()

    @server.list_tools()
    async def handle_list_tools() -> mcp_types.ListToolsResult:
        return mcp_types.ListToolsResult(tools=registry.tool_definitions)

    @server.call_tool()
    async def handle_call_tool(tool_name: str, arguments: dict[str, Any]):
        async with tool_lock:
            entry = registry.resolve_tool_name(tool_name)
            request_override = None
            if arguments:
                maybe_request = arguments.get("request")
                if maybe_request is not None and not isinstance(maybe_request, str):
                    raise ValueError("The 'request' argument must be a string when provided.")
                request_override = maybe_request
            try:
                run_result = await run_agent_workflow(entry, registry.config, request_override)
                text = format_run_result(entry, run_result)
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=text)],
                    isError=False,
                )
            except Exception as exc:  # pragma: no cover - surfaced to MCP client
                return mcp_types.CallToolResult(
                    content=[mcp_types.TextContent(type="text", text=f"Agent '{entry.alias}' failed: {exc}")],
                    isError=True,
                )

    async with stdio_server() as (read_stream, write_stream):
        initialization = server.create_initialization_options()
        await server.run(read_stream, write_stream, initialization)

    return 0


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
            run_result = asyncio.run(run_agent_workflow(entry, config, args.request))
            print(format_run_result(entry, run_result))
            return 0
        except Exception as exc:  # pragma: no cover - CLI surface
            print(f"codex-sub-agent failed: {exc}", file=sys.stderr)
            return 1

    ensure_openai_setup(config)
    try:
        asyncio.run(serve(config, registry))
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
