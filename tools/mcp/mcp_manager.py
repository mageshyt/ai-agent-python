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
        self._prepared = False
        self._background_tasks : asyncio.Task | None = None
        self._registered_tool_names: set[str] = set()



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


    def _prepare_clients(self) -> None:
        if self._prepared:
            return
        mcp_configs = self.config.mcp_servers
        if not mcp_configs:
            self._prepared = True
            return

        for name , mcp_config in mcp_configs.items():
            if not mcp_config.enable:
                continue

            self._clients[name] = MCPClient(
                    name = name,
                    config = mcp_config,
                    cwd = self.config.cwd,
            )
        self._prepared = True

    async def initialize(self):
        if self._initialized:
            return

        self._prepare_clients()

        if not self._clients:
            self._initialized = True
            return

        connection_tasks = [
                asyncio.wait_for(client.connect(),timeout = client.config.startup_timeout)
                for _ , client in self._clients.items()
        ]

        await asyncio.gather(*connection_tasks, return_exceptions=True)

        self._initialized = True

    def start_background_tasks(self,tool_registry:ToolRegistry )->None:

        if self._initialized:
            self.register_tools(tool_registry)
            return

        if self._background_tasks is not None and not self._background_tasks.done():
            return

        async def runner():
            await self.initialize()
            self.register_tools(tool_registry)


        self._background_tasks = asyncio.create_task(runner())


    def register_tools(self, tool_registry:ToolRegistry)->int:
        # we already filter the to get only the connected clients, so we can be sure that the tools are available
        registered_count = 0
        for name, client in self._clients.items():
            if client.status != MCPServerStatus.CONNECTED:
                continue

            for tool_info in client.tools:
                tool_name = f"{name}_{tool_info.name}"
                if tool_name in self._registered_tool_names:
                    continue

                tool = MCPTool(
                        config = self.config,
                        client = client,
                        tool_info = tool_info,
                        name = tool_name,
                )
                tool_registry.register_tool(tool)
                self._registered_tool_names.add(tool_name)
                registered_count += 1
        
        return registered_count

    async def shutdown(self):
        if self._background_tasks is not None and not self._background_tasks.done():
            self._background_tasks.cancel()
            try:
                await self._background_tasks
            except asyncio.CancelledError:
                pass

        self._background_tasks = None

        if not self._initialized:
            return
        shutdown_tasks = [
                client.disconnect() for client in self._clients.values()
        ]

        await asyncio.gather(*shutdown_tasks, return_exceptions=True)   
        self._clients.clear()
        self._initialized = False
        self._prepared = False
        self._registered_tool_names.clear()
