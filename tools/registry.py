from pathlib import Path
from typing import Any
from config.config import Config
from tools import Tool
import logging

from tools.base import ToolInvocation, ToolResult
from tools.builtin import  get_all_builtin_tools


logger = logging.getLogger(__name__)
class ToolRegistry:
    def __init__(self,config:Config) -> None:
        self._tools:dict[str,Tool] = {}
        self.config = config


    def register_tool(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' is already registered. Overwriting.")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister_tool(self, name: str) -> bool:
        if name not in self._tools:
            logger.warning(f"Tool '{name}' not found in registry. Cannot unregister.")
            return False
        del self._tools[name]
        logger.info(f"Unregistered tool: {name}")
        return True

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_tools(self) -> list[Tool]:
        tools: list[Tool] = []
        # add our local tools first

        for tool in self._tools.values():
            tools.append(tool)

        if self.config.allowed_tools is not None:
        # NOTE: Filter by allowed tools if specified in config
            allowed_tool_names = set(self.config.allowed_tools)
            tools = [tool for tool in tools if tool.name in allowed_tool_names]

        # NOTE: we will be adding mcp tools later, so we will keep the order of local tools first, then mcp tools
        return tools


    async def invoke_tool(self, name: str, params: dict[str, Any],cwd:Path|None) -> ToolResult:
        tool = self.get_tool(name)
        if not tool:
            logger.error(f"Tool '{name}' not found in registry. Cannot invoke.")
            return ToolResult.error_result(f"Tool '{name}' not found in registry.",metadata={"tool_name": name})

        # validate params before invoking the tool
        validation_errors = tool.validate_params(params)
        if validation_errors:
            error_message = f"Parameter validation failed for tool '{name}': " + "; ".join(validation_errors)
            logger.error(error_message)
            return ToolResult.error_result(error_message, metadata={"tool_name": name, "validation_errors": validation_errors})

        if cwd is None:
            cwd = Path.cwd() # default to current working directory if not provided

        try:
            invocation = ToolInvocation(cwd=cwd, params=params)
            result = await tool.execute(invocation)
            return result
        except Exception as e:
            logger.exception(f"Error invoking tool '{name}': {str(e)}")
            return ToolResult.error_result(f"Error invoking tool '{name}': {str(e)}", metadata={"tool_name": name})



    def get_tool(self, name: str) -> Tool | None:
        if name not in self._tools:
            logger.warning(f"Tool '{name}' not found in registry.")
            return None
        return self._tools.get(name)


def create_tool_registry(config:Config) -> ToolRegistry:
    registry = ToolRegistry(config)
    for tool in get_all_builtin_tools():
        registry.register_tool(tool(config))

    return registry






