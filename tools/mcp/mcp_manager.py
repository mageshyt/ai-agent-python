import asyncio
from typing import Any

from config.config import Config
from tools.mcp.client import MCPClient,MCPServerStatus
from tools.mcp.mcp_tool import MCPTool
from tools.registry import ToolRegistry


class MCPManager:
    def __init__(self, config: Config):
        self.config = config
        self._clients :dict[str, MCPClient] = {}
        self._initialized = False


    def get_all_servers(self)->list[dict[str,Any]]:
        servers = []

        for name,client in self._clients.items():
            status = client.status

            servers.append({
                "name": name,
                "status": status.value if status else "unknown",
                "tools": len(client.tools) if client.tools else 0,
            })
        return servers

    async def initialize(self):
        if self._initialized:
            return

        mcp_configs = self.config.mcp_servers

        if not mcp_configs:
            return

        for name , mcp_config in mcp_configs.items():
            if not mcp_config.enable:
                continue

            self._clients[name] = MCPClient(
                    name = name,
                    config = mcp_config,
                    cwd = self.config.cwd,
            )
        
        connection_tasks = [
                asyncio.wait_for(client.connect(),timeout = client.config.startup_timeout)
                for name, client in self._clients.items()
        ]

        await asyncio.gather(*connection_tasks, return_exceptions=True)

        self._initialized = True


    def register_tools(self, tool_registry:ToolRegistry)->int:
        # we already filter the to get only the connected clients, so we can be sure that the tools are available
        registered_count = 0
        for name, client in self._clients.items():
            if client.status != MCPServerStatus.CONNECTED:
                continue

            for tool_info in client.tools:
                tool = MCPTool(
                        config = self.config,
                        client = client,
                        tool_info = tool_info,
                        name = f"{name}_{tool_info.name}",
                )
                tool_registry.register_tool(tool)
                registered_count += 1
        
        return registered_count

    async def shutdown(self):
        shutdown_tasks = [
                client.disconnect() for client in self._clients.values()
        ]

        await asyncio.gather(*shutdown_tasks, return_exceptions=True)   
        self._initialized = False

