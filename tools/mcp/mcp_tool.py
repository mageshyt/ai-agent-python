import asyncio
from typing import Any
from config.config import Config

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.mcp.client import MCPClient, MCPToolInfo, MCPServerStatus


class MCPTool(Tool):
    def __init__(
            self,
            config:Config,
            client:MCPClient,
            tool_info:MCPToolInfo,
            name:str,
    )->None:
        super().__init__(config )
        self.client = client
        self.tool_info = tool_info
        self.name = name
        self.kind = ToolKind.MCP
        self.description = tool_info.description


    def is_mutating(self) -> bool:
        return True

    @property
    def schema(self)->dict[str,Any]:
        input_schema = self.tool_info.input_schema or {}

        return {
                "type": "object",
                "properties": input_schema.get("properties", {}),
                "required": input_schema.get("required", []),
        }


    async def execute(self, invocation:ToolInvocation)->ToolResult:
        params = invocation.params
        try:
            if self.client.status != MCPServerStatus.CONNECTED:
                await asyncio.wait_for(
                    self.client.connect(),
                    timeout=self.client.config.startup_timeout,
                )

            result = await self.client.call_tool(self.tool_info.name, params)
            output = result.get("output", {})
            is_error = result.get("is_error", False)

            if is_error:
                return ToolResult.error_result(output)

            return ToolResult.success_result(output)
        except asyncio.TimeoutError:
            return ToolResult.error_result(
                f"MCP server '{self.client.name}' startup timed out"
            )
        except Exception as e:
            return ToolResult.error_result(f"MCP tool called failed {str(e)}")
