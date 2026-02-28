from typing import AsyncGenerator

from agent.events import AgentEvent
from lib.response import EventType
from llm.client import LLMProvider


class Agent:
    def __init__(self ):
        self.client = LLMProvider()


    async def  _agentic_loop(self)->AsyncGenerator[AgentEvent, None]:
        message = [
            {
                "role": "user",
                "content": "What is the capital of France?"
            }
        ]
        async for event in self.client.send_message(message, stream=True):
            if event.type == EventType.TEXT_DELTA:
                content = event.text_delta.content if event.text_delta else ""
                yield AgentEvent.text_delta(agent_name="example_agent", content=content)
            elif event.type == EventType.ERROR:
                error_message = event.error if event.error else "Unknown error"
                yield AgentEvent.agent_error(agent_name="example_agent", message=error_message)
            elif event.type == EventType.MESSAGE_COMPLETE:
                usage = event.usage
                content = event.text_delta.content if event.text_delta else ""
                yield AgentEvent.agent_finished(agent_name="example_agent", response=content, usage=usage)
