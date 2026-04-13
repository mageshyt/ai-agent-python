from llm.client import LLMProvider 
from context.context_manager import ContextManager
class ChatCompactor:
    def __init__(self,client: LLMProvider):
        self.client = client

    async def compress(self,context_manager:ContextManager ):
        pass


