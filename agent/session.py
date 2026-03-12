import uuid
from datetime import datetime

from config.config import Config
from context.context_manager import ContextManager
from llm.client import LLMProvider
from tools.registry import create_tool_registry


class Session:
    def __init__(self,config:Config):
        self.client = LLMProvider(config)
        self.agentId : str = "ask_agent"
        self.context_manager = ContextManager(config)
        self.tool_registry = create_tool_registry()
        self.config = config
        self.sessionId = str(uuid.uuid4())
        self.createdAt = datetime.now()
        self.updatedAt = datetime.now()

        self._turn_count = 0 # to track the number of turns in the session


    def increment_turn(self)->int:
        self._turn_count += 1
        self.updatedAt = datetime.now()
        return self._turn_count

