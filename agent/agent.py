from __future__ import annotations
from typing import AsyncGenerator

from agent.events import AgentEvent, AgentEventType
from lib.response import EventType
from llm.client import LLMProvider


class Agent:
    def __init__(self ):
        self.client = LLMProvider()
        self.agentId : str = "example_agent"
    
    async def run(self,mesage:str)->AsyncGenerator[AgentEvent, None]:
        yield AgentEvent.agent_started(agent_name=self.agentId , message=mesage)
        final_response:str | None = None
        async for event in self._agentic_loop(mesage):
            yield event
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content") if event.data.get("content") else "No content"

        yield AgentEvent.agent_finished(agent_name=self.agentId , response=final_response, usage=None)


    async def  _agentic_loop(self,message_content:str)->AsyncGenerator[AgentEvent, None]:
        message = [
            {
                "role": "user",
                "content": message_content
            }
        ]

        if (not self.client):
            yield AgentEvent.agent_error(agent_name=self.agentId, message="LLM client is not initialized.")
            return

        response_text = ""

        async for event in self.client.send_message(message, stream=True):
            if event.type == EventType.TEXT_DELTA:
                content = event.text_delta.content if event.text_delta else ""
                response_text += content
                yield AgentEvent.text_delta(agent_name="example_agent", content=content)
            elif event.type == EventType.ERROR:
                error_message = event.error if event.error else "Unknown error"
                yield AgentEvent.agent_error(agent_name="example_agent", message=error_message)
    
        if response_text:
            yield AgentEvent.text_complete(agent_name=self.agentId, content=response_text)
    
    async def _check_for_agent(self) :
        if not self.agentId:
            yield AgentEvent.agent_error(agent_name="example_agent", message="Agent ID is not set. Please set the agent ID before running the agent.")
        
    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.client:
            await self.client.close()
            self.client = None
