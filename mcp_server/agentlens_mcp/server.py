from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any, cast

from agentlens_client.async_client import AgentLensAsyncClient

from agentlens_mcp.config import Args
from agentlens_mcp.errors import invalid_params
from agentlens_mcp.tools import TOOL_DEFINITIONS, AgentLensMcpTools

McpServer: Any | None
StdioServer: Any | None
TextContent: Any | None
Tool: Any | None

if TYPE_CHECKING:
    from mcp.server import Server

try:  # pragma: no cover - exercised when the mcp package is installed.
    from mcp.server import Server as _McpServer
    from mcp.server.stdio import stdio_server as _stdio_server
    from mcp.types import TextContent as _TextContent
    from mcp.types import Tool as _Tool
except ModuleNotFoundError:  # pragma: no cover - local tests run without mcp installed.
    McpServer = None
    StdioServer = None
    TextContent = None
    Tool = None
else:  # pragma: no cover - exercised when the mcp package is installed.
    McpServer = _McpServer
    StdioServer = _stdio_server
    TextContent = _TextContent
    Tool = _Tool

TOOL_NAMES = {tool.name for tool in TOOL_DEFINITIONS}


def create_server(
    backend_url: str,
    author: str,
    timeout: int = 30,
) -> Server:
    if McpServer is None or TextContent is None or Tool is None:
        raise RuntimeError("The mcp package is required to run agentlens-mcp.")

    client = AgentLensAsyncClient(base_url=backend_url, timeout=timeout)
    toolset = AgentLensMcpTools(
        client=client,
        backend_url=backend_url,
        author=author,
        timeout=timeout,
    )
    server = McpServer("agentlens-mcp")

    @server.list_tools()  # type: ignore[misc]
    async def list_tools() -> list[Any]:
        return [
            Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema,
            )
            for tool in TOOL_DEFINITIONS
        ]

    @server.call_tool()  # type: ignore[misc]
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[Any]:
        result = await _dispatch_tool(toolset, name, arguments or {})
        return [TextContent(type="text", text=_format_tool_result(result))]

    server._agentlens_toolset = toolset
    return server


async def run_server(args: Args) -> None:
    if StdioServer is None:
        raise RuntimeError("The mcp package is required to run agentlens-mcp.")
    configure_logging()
    server = create_server(
        backend_url=args.backend_url,
        author=args.author,
        timeout=args.timeout,
    )
    try:
        async with StdioServer() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        toolset = cast(AgentLensMcpTools | None, getattr(server, "_agentlens_toolset", None))
        if toolset is not None:
            await toolset.close()


def configure_logging() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)


async def _dispatch_tool(
    toolset: AgentLensMcpTools,
    name: str,
    arguments: dict[str, Any],
) -> Any:
    if name not in TOOL_NAMES:
        raise invalid_params(f"Unknown AgentLens tool: {name}")
    method = getattr(toolset, name)
    return await method(**arguments)


def _format_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, indent=2, default=str)


__all__ = ["configure_logging", "create_server", "run_server"]
