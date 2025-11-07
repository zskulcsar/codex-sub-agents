"""Utilities for loading and validating sub-agent configuration files."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Literal, Union

import tomllib
from pydantic import BaseModel, Field, ValidationError


class OpenAISettings(BaseModel):
    """OpenAI platform settings that apply to every sub-agent run."""

    api_key_env_var: str = Field(default="OPENAI_API_KEY")
    default_api: Literal["responses", "chat_completions"] = Field(default="responses")


class AgentSettings(BaseModel):
    """Concrete configuration for a single sub-agent role."""

    name: str
    model: str = Field(default="gpt-5")
    instructions: str
    entry_message: str
    temperature: float | None = Field(default=None)
    reasoning_tokens: int | None = Field(default=None)
    mcp_servers: list[str] = Field(default_factory=list)


class MCPStdioConfig(BaseModel):
    """Definition for launching an MCP server over stdio."""

    type: Literal["stdio"]
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    client_session_timeout_seconds: float = Field(default=300.0)


class MCPHttpConfig(BaseModel):
    """Definition for connecting to an MCP server over HTTP(S)."""

    type: Literal["http"]
    name: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    bearer_token_env_var: str | None = None
    client_session_timeout_seconds: float = Field(default=60.0)


MCPConfig = Union[MCPStdioConfig, MCPHttpConfig]


class SubAgentConfig(BaseModel):
    """Aggregate data model describing all sub-agent runtime requirements."""

    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    agent: AgentSettings | None = None
    agents: Dict[str, AgentSettings] = Field(default_factory=dict)
    default_agent_id: str | None = None
    aliases: Dict[str, str] = Field(default_factory=dict)
    mcp_servers: Dict[str, MCPConfig] = Field(default_factory=dict)

    model_config = {"use_enum_values": True, "populate_by_name": True}

    def _agent_map(self) -> Dict[str, AgentSettings]:
        """Return a mapping of agent identifiers to their settings."""

        mapping: Dict[str, AgentSettings] = dict(self.agents)
        if self.agent is not None:
            mapping.setdefault("default", self.agent)
        return mapping

    def available_agents(self) -> Dict[str, AgentSettings]:
        """List all configured agents, ensuring at least one exists."""

        agents = self._agent_map()
        if not agents:
            raise InvalidConfiguration("Configuration must define at least one agent.")
        return agents

    def resolve_agent(self, agent_id: str | None) -> tuple[str, AgentSettings]:
        """Resolve an agent identifier (or alias) to concrete settings.

        Args:
            agent_id: Explicit identifier or alias supplied by the user. When ``None``,
                the configuration's default agent is selected.

        Returns:
            A tuple containing the canonical agent identifier and its settings.

        Raises:
            InvalidConfiguration: If the requested agent (or alias) is unknown.
        """

        agents = self.available_agents()
        if agent_id:
            resolved_id = self.aliases.get(agent_id, agent_id)
            if resolved_id not in agents:
                raise InvalidConfiguration(
                    f"Agent '{agent_id}' not found. Available agents: {', '.join(sorted(agents))}"
                )
            return resolved_id, agents[resolved_id]

        if self.default_agent_id:
            if self.default_agent_id not in agents:
                raise InvalidConfiguration(
                    f"default_agent '{self.default_agent_id}' is not defined in agents."
                )
            return self.default_agent_id, agents[self.default_agent_id]

        chosen = sorted(agents)[0]
        return chosen, agents[chosen]


class InvalidConfiguration(Exception):
    """Raised when the configuration file cannot be parsed."""


def load_config(config_path: Path) -> SubAgentConfig:
    """Load and validate a TOML configuration file.

    The loader supports inline agent definitions or external agent files declared via
    ``agent_files``. External entries are resolved relative to the main configuration.

    Args:
        config_path: Path to the root TOML file.

    Returns:
        Fully hydrated :class:`SubAgentConfig` instance.

    Raises:
        InvalidConfiguration: If the file or an included agent file is missing or
            malformed.
    """

    def _load_agent_dir(agent_path: Path) -> tuple[str, Dict[str, object]]:
        """Read an agent directory containing TOML + Markdown assets."""

        if not agent_path.is_dir():
            raise InvalidConfiguration(
                f"Agent path {agent_path} must be a directory containing agent.toml, "
                "entry_message.md, and instructions.md."
            )

        toml_path = agent_path / "agent.toml"
        instructions_path = agent_path / "instructions.md"
        entry_path = agent_path / "entry_message.md"

        try:
            with toml_path.open("rb") as fh:
                agent_payload = tomllib.load(fh)
        except FileNotFoundError as exc:
            raise InvalidConfiguration(f"Agent file not found: {toml_path}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise InvalidConfiguration(f"Failed to parse agent file {toml_path}: {exc}") from exc

        agent_id = agent_payload.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            raise InvalidConfiguration(
                f"Agent file {toml_path} is missing a non-empty 'id' field."
            )

        if "agent" in agent_payload:
            agent_data = agent_payload["agent"]
        else:
            agent_data = {k: v for k, v in agent_payload.items() if k != "id"}

        if not isinstance(agent_data, dict):
            raise InvalidConfiguration(
                f"Agent file {toml_path} must define agent settings under an 'agent' table."
            )

        def _load_markdown(markdown_path: Path, label: str) -> str:
            try:
                content = markdown_path.read_text(encoding="utf-8").strip()
            except FileNotFoundError as exc:
                raise InvalidConfiguration(
                    f"Agent directory {agent_path} is missing {label} file: {markdown_path.name}"
                ) from exc
            if not content:
                raise InvalidConfiguration(
                    f"{label.capitalize()} in {markdown_path} must not be empty."
                )
            return content

        agent_data["instructions"] = _load_markdown(instructions_path, "instructions")
        agent_data["entry_message"] = _load_markdown(entry_path, "entry message")

        return agent_id, agent_data

    try:
        with config_path.open("rb") as fh:
            payload = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise InvalidConfiguration(f"Configuration file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise InvalidConfiguration(f"Failed to parse TOML configuration: {exc}") from exc

    base_dir = config_path.parent

    agent_files = payload.pop("agent_files", [])
    if agent_files:
        if not isinstance(agent_files, list):
            raise InvalidConfiguration("'agent_files' must be a list of file paths.")

        agents_table = payload.setdefault("agents", {})
        if not isinstance(agents_table, dict):
            raise InvalidConfiguration("'agents' section must be a table.")

        for index, rel_path in enumerate(agent_files):
            if not isinstance(rel_path, str):
                raise InvalidConfiguration(f"agent_files[{index}] must be a string path.")
            file_path = (base_dir / rel_path).resolve()
            agent_id, agent_data = _load_agent_dir(file_path)
            if agent_id in agents_table:
                raise InvalidConfiguration(
                    f"Duplicate agent id '{agent_id}' defined in {file_path}."
                )
            agents_table[agent_id] = agent_data

    if "default_agent" in payload and "default_agent_id" not in payload:
        payload["default_agent_id"] = payload["default_agent"]

    try:
        cfg = SubAgentConfig.model_validate(payload)
    except ValidationError as exc:
        raise InvalidConfiguration(f"Invalid configuration: {exc}") from exc

    if "codex" not in cfg.mcp_servers:
        raise InvalidConfiguration(
            "Missing required MCP server 'codex'. Add `[mcp_servers.codex]` to codex_sub_agents.toml."
        )

    return cfg
