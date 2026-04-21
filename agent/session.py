import uuid
import asyncio
from datetime import datetime

from config.config import Config
from context.compaction import ChatCompactor
from context.context_manager import ContextManager
from context.pruning import PruningConfig, SlidingWindowPruner
from llm.client import LLMProvider
from tools.discovery import ToolDiscoveryManger
from tools.mcp.mcp_manager import MCPManager
from tools.registry import create_tool_registry


class Session:
    def __init__(self,config:Config):
        self.client = LLMProvider(config)
        self.agentId : str = "agent_black"
        self.tool_registry = create_tool_registry(config)
        self.context_manager = None
        self.config = config
        self.discovery_manager = ToolDiscoveryManger(config,self.tool_registry)
        self.mcp_manager = MCPManager(config)
        self.chat_compactor = ChatCompactor(self.client)
        self.prune_manager = SlidingWindowPruner(
            PruningConfig(
                max_window_tokens=config.pruning.max_window_tokens,
                keep_recent_messages=config.pruning.keep_recent_messages,
                keep_recent_tool_results=config.pruning.keep_recent_tool_results,
                preserve_system=config.pruning.preserve_system,
                preserve_sticky=config.pruning.preserve_sticky,
                sticky_keywords=list(config.pruning.sticky_keywords),
            )
        )

        self.sessionId = str(uuid.uuid4())
        self.createdAt = datetime.now()
        self.updatedAt = datetime.now()
        self._turn_count = 0 # to track the number of turns in the session

    async def initialize(self):
        self.mcp_manager.start_background_tasks(self.tool_registry)
        self.discovery_manager.discover_all() # discover tools again after registering mcp tools, so that we can update the tool registry with the new tools
        self.context_manager = ContextManager(self.config,tools=self.tool_registry.get_tools())


    def increment_turn(self)->int:
        self._turn_count += 1
        self.updatedAt = datetime.now()
        return self._turn_count
