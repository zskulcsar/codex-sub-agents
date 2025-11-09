"""MCP server orchestration for exposing configured agents as tools."""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any, Iterable

from agents import Runner, Tool
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
from .agent_runtime import AgentAliasEntry, AgentRegistry
from .config_models import MCPHttpConfig, MCPStdioConfig, SubAgentConfig


async def serve(config: SubAgentConfig, registry: AgentRegistry) -> int:
    """Expose configured agents as MCP tools over stdio."""

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


def format_run_result(alias_entry: AgentAliasEntry, result: Any) -> str:
    """Render the final output of an agent run for CLI/MCP responses.

    Args:
        alias_entry: Alias metadata whose blueprint supplies fallback names.
        result: Raw result object returned by :func:`agents.Runner.run`.

    Returns:
        A human-readable string summarizing the run outcome.
    """

    final_output = getattr(result, "final_output", None)
    if isinstance(final_output, str) and final_output.strip():
        return final_output
    if final_output:
        try:
            import json

            return json.dumps(final_output, indent=2, default=str)
        except Exception:  # pragma: no cover
            return str(final_output)

    last_agent = getattr(result, "last_agent", None)
    last_agent_name = last_agent.name if last_agent else alias_entry.blueprint.settings.name
    return f"Agent '{alias_entry.alias}' completed via {last_agent_name}, but no final output was produced."


async def run_agent_workflow(alias_entry: AgentAliasEntry, config: SubAgentConfig, requested_prompt: str | None):
    """Execute a configured agent end-to-end.

    Args:
        alias_entry: Agent alias/blueprint describing model settings and servers.
        config: Validated configuration containing MCP server definitions.
        requested_prompt: Optional override for the agent's default prompt.

    Returns:
        Whatever :func:`agents.Runner.run` returns for the invoked agent.
    """

    servers, exit_stack = await initialize_mcp_servers(config, alias_entry.blueprint.mcp_server_names)
    try:
        tools: list[Tool] = [skill.build_tool() for skill in alias_entry.blueprint.settings.skills]
        agent = alias_entry.blueprint.build_agent(tools=tools, mcp_servers=list(servers.values()))
        entry = requested_prompt or alias_entry.blueprint.settings.default_prompt
        return await Runner.run(agent, entry)
    finally:
        await exit_stack.aclose()


__all__ = ["serve", "run_agent_workflow", "format_run_result", "initialize_mcp_servers"]
async def initialize_mcp_servers(
    config: SubAgentConfig,
    server_names: Iterable[str],
) -> tuple[dict[str, MCPServer], AsyncExitStack]:
    """Start the MCP servers requested by ``server_names``.

    Args:
        config: Full configuration with named MCP server definitions.
        server_names: Sequence of server names required by the agent.

    Returns:
        A tuple of (``name -> server`` map, active :class:`AsyncExitStack`). The caller
        must close the exit stack when the run completes.

    Raises:
        InvalidConfiguration: If a referenced server name is unknown.
        RuntimeError: If an HTTP server requires authentication that is missing.
    """

    servers: dict[str, MCPServer] = {}
    exit_stack = AsyncExitStack()
    await exit_stack.__aenter__()

    unique_names = list(dict.fromkeys(server_names))

    for name in unique_names:
        server_config = config.mcp_servers.get(name)
        if server_config is None:
            await exit_stack.aclose()
            from .config_models import InvalidConfiguration

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
