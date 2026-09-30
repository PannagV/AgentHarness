from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

"""Configuration and client lifecycle for project and external MCP servers."""

@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: Literal["stdio", "sse", "http"]
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class ServerStatus:
    config: MCPServerConfig
    client: Any = None
    tools: list[Any] = field(default_factory=list)
    error: str | None = None


class MCPManager:
    """Manage configured MCP connections and expose model-compatible tools."""

    def __init__(self, project_root: Path | str, config_path: Path | str | None = None):
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path) if config_path else self.project_root / "mcp" / "servers.yaml"
        if not self.config_path.is_absolute():
            self.config_path = self.project_root / self.config_path
        self.servers: dict[str, ServerStatus] = {}
        self._tool_bindings: dict[str, tuple[str, str, Any]] = {}
        self.load_errors: dict[str, str] = {}

    def load_config(self) -> list[MCPServerConfig]:
        if not self.config_path.is_file():
            return []
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict) or not isinstance(raw.get("servers", []), list):
            raise ValueError("MCP configuration must contain a 'servers' list")

        configs: list[MCPServerConfig] = []
        names: set[str] = set()
        self.load_errors.clear()
        for index, item in enumerate(raw.get("servers", [])):
            label = (
                item.get("name", f"server[{index}]")
                if isinstance(item, dict)
                else f"server[{index}]"
            )
            try:
                config = self._parse_config(item)
                label = config.name
                if config.name.casefold() in names:
                    raise ValueError(f"duplicate MCP server name: {config.name}")
                names.add(config.name.casefold())
                if config.enabled:
                    configs.append(config)
            except (TypeError, ValueError) as error:
                self.load_errors[label] = str(error)
        return configs

    def _parse_config(self, item: Any) -> MCPServerConfig:
        if not isinstance(item, dict):
            raise ValueError("server entry must be a mapping")
        name = item.get("name")
        transport = item.get("transport", "stdio")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("server requires a non-empty name")
        if transport not in {"stdio", "sse", "http"}:
            raise ValueError(f"unsupported transport: {transport}")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        env = self._expand_mapping(item.get("env", {}), "env")
        headers = self._expand_mapping(item.get("headers", {}), "headers")
        if transport == "stdio":
            command = item.get("command")
            args = item.get("args", [])
            if not isinstance(command, str) or not command.strip():
                raise ValueError("stdio server requires a command")
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                raise ValueError("args must be a list of strings")
            cwd_value = item.get("cwd")
            cwd = None
            if cwd_value:
                cwd = Path(cwd_value).expanduser()
                if not cwd.is_absolute():
                    cwd = (self.project_root / cwd).resolve()
            return MCPServerConfig(name.strip(), transport, command, tuple(args), cwd, env, enabled=enabled)
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValueError(f"{transport} server requires an http(s) URL")
        return MCPServerConfig(name.strip(), transport, url=url, headers=headers, enabled=enabled)

    @staticmethod
    def _expand_mapping(value: Any, field_name: str) -> dict[str, str]:
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise ValueError(f"{field_name} must be a mapping of strings")
        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

        def expand(text: str) -> str:
            def replace(match: re.Match[str]) -> str:
                variable = match.group(1)
                if variable not in os.environ:
                    raise ValueError(f"environment variable {variable} is not set")
                return os.environ[variable]
            return pattern.sub(replace, text)

        return {key: expand(item) for key, item in value.items()}

    async def connect_all(self) -> None:
        try:
            configs = self.load_config()
        except (OSError, yaml.YAMLError, ValueError) as error:
            self.load_errors[str(self.config_path)] = str(error)
            return
        for config in configs:
            await self.connect(config)

    async def connect(self, config: MCPServerConfig) -> bool:
        status = ServerStatus(config)
        self.servers[config.name] = status
        try:
            from fastmcp import Client
            from fastmcp.client.transports import SSETransport, StdioTransport, StreamableHttpTransport

            if config.transport == "stdio":
                cwd = config.cwd or self.project_root
                command = config.command or ""
                args = list(config.args)
                script = args[0] if args else ""
                if script and not Path(script).is_absolute() and (cwd / script).exists():
                    args[0] = str((cwd / script).resolve())
                transport = StdioTransport(
                    command=command,
                    args=args,
                    cwd=str(cwd),
                    env={**os.environ, **config.env},
                )
            elif config.transport == "sse":
                transport = SSETransport(config.url or "", headers=config.headers)
            else:
                transport = StreamableHttpTransport(config.url or "", headers=config.headers)
            client = Client(transport)
            await client.__aenter__()
            status.client = client
            status.tools = await client.list_tools()
            self._rebuild_tool_index()
            return True
        except Exception as error:
            status.error = str(error)
            self._rebuild_tool_index()
            return False

    async def disconnect(self, name: str) -> None:
        status = self.servers.pop(name, None)
        if status and status.client:
            try:
                await status.client.__aexit__(None, None, None)
            finally:
                self._rebuild_tool_index()

    async def disconnect_all(self) -> None:
        for name in list(self.servers):
            await self.disconnect(name)

    def _rebuild_tool_index(self) -> None:
        self._tool_bindings.clear()
        for server_name, status in self.servers.items():
            for tool in status.tools:
                original = tool.name
                qualified = self._qualified_name(server_name, original)
                self._tool_bindings[qualified] = (server_name, original, tool)

    @staticmethod
    def _qualified_name(server_name: str, tool_name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", f"mcp__{server_name}__{tool_name}")
        return safe[:64]

    def responses_tools(self) -> list[dict[str, Any]]:
        tools = []
        for qualified, (_, _, tool) in self._tool_bindings.items():
            schema = (
                getattr(tool, "inputSchema", None)
                or getattr(tool, "input_schema", None)
                or {"type": "object", "properties": {}}
            )
            tools.append({
                "type": "function",
                "name": qualified,
                "description": getattr(tool, "description", None) or f"MCP tool {tool.name}",
                "parameters": schema,
            })
        return tools

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> str:
        binding = self._tool_bindings.get(qualified_name)
        if binding is None:
            raise ValueError(f"Unknown MCP tool: {qualified_name}")
        server_name, original, _ = binding
        status = self.servers[server_name]
        result = await status.client.call_tool(original, arguments)
        content = getattr(result, "content", None)
        if content is None:
            return str(result)
        chunks = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                chunks.append(text)
            else:
                chunks.append(str(item))
        output = "\n".join(chunks)
        return output[:50000] + ("\n[Tool output truncated]" if len(output) > 50000 else "")

    def server_summaries(self) -> list[tuple[str, str, str]]:
        summaries = [(name, status.config.transport, "connected" if status.client else status.error or "disconnected")
                     for name, status in self.servers.items()]
        summaries.extend((name, "config", error) for name, error in self.load_errors.items())
        return summaries

    def tool_summaries(self) -> list[tuple[str, str]]:
        return [(name, getattr(tool, "description", None) or "")
                for name, (_, _, tool) in self._tool_bindings.items()]
