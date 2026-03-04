from pathlib import Path
from typing import Any
from tools import Tool
import logging

from tools.base import ToolInvocation, ToolResult
from tools.builtin import  get_all_builtin_tools


logger = logging.getLogger(__name__)
class ToolRegistry:
    def __init__(self) -> None:
        self._tools:dict[str,Tool] = {}


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
        # NOTE: we will be adding mcp tools later, so we will keep the order of local tools first, then mcp tools
        return tools


    async def invoke_tool(self, name: str, params: dict[str, Any],cwd:Path|None) -> Any:
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
            await tool.execute(invocation)
        except Exception as e:
            logger.exception(f"Error invoking tool '{name}': {str(e)}")
            return ToolResult.error_result(f"Error invoking tool '{name}': {str(e)}", metadata={"tool_name": name})



    def get_tool(self, name: str) -> Tool | None:
        if name not in self._tools:
            logger.warning(f"Tool '{name}' not found in registry.")
            return None
        return self._tools.get(name)


def create_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in get_all_builtin_tools():
        registry.register_tool(tool())

    return registry






