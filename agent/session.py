import uuid
import asyncio
from datetime import datetime

from config.config import Config
from context.compaction import ChatCompactor
from context.context_manager import ContextManager
from context.pruning import PruningConfig, SlidingWindowPruner
from hooks.hook_system import HookSystem
from llm.client import LLMProvider
from security.approval_manager import ApprovalManager
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
        self.approval_manager = ApprovalManager(
            approval_policy=config.approval,
            cwd=config.cwd,
        )
        self.hooks = HookSystem(config)

        self.sessionId = str(uuid.uuid4())
        self.createdAt = datetime.now()
        self.updatedAt = datetime.now()
        self._turn_count = 0 # to track the number of turns in the session
        
        # Context stats tracking
        self._stats = {
            "pruning_events": 0,
            "messages_pruned": 0,
            "compaction_events": 0,
            "total_completion_tokens": 0,
            "total_prompt_tokens": 0,
        }

    async def initialize(self):
        self.mcp_manager.start_background_tasks(self.tool_registry)
        self.discovery_manager.discover_all() # discover tools again after registering mcp tools, so that we can update the tool registry with the new tools
        self.context_manager = ContextManager(self.config,tools=self.tool_registry.get_tools())


    def increment_turn(self)->int:
        self._turn_count += 1
        self.updatedAt = datetime.now()
        return self._turn_count
    
    def record_prune_event(self, removed_count: int) -> None:
        """Record a pruning event."""
        self._stats["pruning_events"] += 1
        self._stats["messages_pruned"] += removed_count
        self.updatedAt = datetime.now()
    
    def record_compaction_event(self) -> None:
        """Record a compaction event."""
        self._stats["compaction_events"] += 1
        self.updatedAt = datetime.now()
    
    def record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Record token usage from LLM."""
        self._stats["total_prompt_tokens"] += prompt_tokens
        self._stats["total_completion_tokens"] += completion_tokens
    
    def get_stats(self) -> dict:
        """Get comprehensive session stats."""
        if not self.context_manager:
            return self._stats.copy()
        
        # Compute actual current context window size (includes system prompt + messages)
        from lib.text import count_tokens
        
        system_prompt_tokens = count_tokens(self.context_manager.system_prompts, model=self.config.get_model_name)
        
        messages = self.context_manager._messages
        current_messages_count = len(messages)
        messages_tokens = 0
        for m in messages:
            msg_tokens = m.token_count if m.token_count is not None else count_tokens(m.content, model=self.config.get_model_name)
            messages_tokens += msg_tokens
            
        # Compute tool schemas footprint
        import json
        tools = self.tool_registry.get_schemas()
        tools_tokens = count_tokens(json.dumps(tools), model=self.config.get_model_name) if tools else 0
        
        # Total context sent to model in each request
        current_context_tokens = system_prompt_tokens + messages_tokens + tools_tokens
        
        # Get token usage
        usage = self.context_manager.get_total_usage()
        
        return {
            **self._stats,
            "turn_count": self._turn_count,
            "session_id": self.sessionId,
            "created_at": self.createdAt.isoformat(),
            "updated_at": self.updatedAt.isoformat(),
            "current_messages": current_messages_count,
            "system_prompt_tokens": system_prompt_tokens,
            "messages_tokens": messages_tokens,
            "tools_tokens": tools_tokens,
            "current_context_tokens": current_context_tokens,
            "total_api_tokens_used": usage.total_tokens,
            "api_prompt_tokens": usage.prompt_tokens,
            "api_completion_tokens": usage.completion_tokens,
            "api_cached_tokens": usage.cached_tokens,
            "pruning_budget": self.prune_manager.config.max_window_tokens,
            "context_window": self.config.model.context_window,
        }

    def get_message_details(self) -> list[dict]:
        """Return a list of stored messages with token counts and short preview.

        Each item: {index, role, token_count, preview}
        """
        details: list[dict] = []
        if not self.context_manager:
            return details

        for i, m in enumerate(self.context_manager._messages):
            preview = (m.content[:400] + "...[truncated]") if m.content and len(m.content) > 400 else (m.content or "")
            details.append({
                "index": i,
                "role": m.role,
                "token_count": m.token_count or (0 if not m.content else None),
                "preview": preview,
            })

        return details
