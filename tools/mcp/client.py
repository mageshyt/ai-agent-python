import os
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport

from config.config import MCPServerConfig


@dataclass
class MCPToolInfo:
    name : str
    description: str
    input_schema : dict[str,Any] = field(default_factory=dict)
    server_name:str = ""

class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

class MCPClient:
    def __init__(self,name:str,config:MCPServerConfig,cwd:Path)->None:
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self._client:Client | None = None
        self._tools:dict[str,MCPToolInfo] = dict()



    @property
    def tools(self)->list[MCPToolInfo]:
        return list(self._tools.values())

    def _create_transport(self)-> StdioTransport | SSETransport:
        # if the config has command then use StdioTransport

        if self.config.command:
            env = os.environ.copy()
            # update the env
            env.update(self.config.env)

            return StdioTransport(
                        command=self.config.command,
                        args=list(self.config.args),
                        env=env,
                        cwd=str(self.config.cwd or self.cwd),
                        log_file=Path(os.devnull),
            )
        else:
            return SSETransport(url=self.config.url)

    async def connect(self)->None:
        if self.status == MCPServerStatus.CONNECTED:
            return 

        self.status = MCPServerStatus.CONNECTING

        try:
            self._client = Client(transport = self._create_transport())

            await self._client.__aenter__()


            tool_result = await self._client.list_tools()

            for tool in tool_result:
                self._tools[tool.name] = MCPToolInfo(
                        name = tool.name,
                        description= tool.description or "",
                        input_schema=(
                            tool.inputSchema if hasattr(tool,"inputSchema") else {}
                        ),
                        server_name= self.name
                )

            self.status = MCPServerStatus.CONNECTED

        except asyncio.CancelledError:
            self.status = MCPServerStatus.ERROR
            await self._safe_close_client()
            raise

        except Exception as e:
            self.status = MCPServerStatus.ERROR
            await self._safe_close_client()
            raise e


    async def disconnect(self) -> None:
        await self._safe_close_client()
        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED

    async def _safe_close_client(self) -> None:
        if not self._client:
            return

        client = self._client
        self._client = None
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            # Best effort cleanup; shutdown should continue even if close fails.
            pass

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]):
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Not connected to server {self.name}")

        result = await self._client.call_tool(tool_name, arguments)

        output = []
        for item in result.content:
            if hasattr(item, "text"):
                output.append(item.text)
            else:
                output.append(str(item))

        return {
            "output": "\n".join(output),
            "is_error": result.is_error,
        }
