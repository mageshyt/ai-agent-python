from __future__ import annotations
from pathlib import Path
from typing import AsyncGenerator

from rich import console

from agent.events import AgentEvent, AgentEventType
from context.context_manager import ContextManager
from lib.response import StreamEventType, ToolCall, ToolResultMessage
from llm.client import LLMProvider
from tools.registry import create_tool_registry


class Agent:
    def __init__(self ):
        self.client = LLMProvider()
        self.agentId : str = "ask_agent"
        self.context_manager = ContextManager()
        self.tool_registry = create_tool_registry()
    
    async def run(self,mesage:str)->AsyncGenerator[AgentEvent, None]:
        yield AgentEvent.agent_started(agent_name=self.agentId , message=mesage)
        self.context_manager.add_user_message(mesage)
        final_response:str | None = None
        async for event in self._agentic_loop():
            yield event
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content") if event.data.get("content") else "No content"

        yield AgentEvent.agent_finished(agent_name=self.agentId , response=final_response, usage=None)


    async def  _agentic_loop(self)->AsyncGenerator[AgentEvent, None]:
        message = self.context_manager.get_context()
        tools = self.tool_registry.get_schemas()
        tool_calls:list[ToolCall] = []

        if (not self.client):
            yield AgentEvent.agent_error(agent_name=self.agentId, message="LLM client is not initialized.")
            return

        response_text = ""

        async for event in self.client.send_message(message, tools = tools if tools else None, stream=True):
            if event.type == StreamEventType.TEXT_DELTA:
                content = event.text_delta.content if event.text_delta else ""
                response_text += content
                yield AgentEvent.text_delta(agent_name=self.agentId, content=content)
            elif event.type == StreamEventType.ERROR:
                error_message = event.error if event.error else "Unknown error"
                yield AgentEvent.agent_error(agent_name=self.agentId, message=error_message)

            elif event.type == StreamEventType.TOOL_CALL_END:
                # we have a complete tool call, now we can execute it
                if event.tool_call:
                    tool_calls.append(event.tool_call)
    
        #NOTE: we will add the assistant message to the context manager after the response is complete, so that we have the full response text available for token counting and other processing if needed. This also allows us to yield a text_complete event with the full response text.
        tool_calls_data = [ tool_call.to_dict() for tool_call in tool_calls ] if tool_calls else []
        print(f"Tool calls data: {tool_calls}")
        self.context_manager.add_assistant_message(response_text,tool_calls=tool_calls_data)
        if response_text:
            yield AgentEvent.text_complete(agent_name=self.agentId, content=response_text)
        
        tool_call_result:list[ToolResultMessage] = []
        # invoke all the tool calls sequentially, we can optimize this later by running them in parallel if they are independent of each other
        for tool_call in tool_calls:
                # this event is to display the call in the UI
                tool_name = tool_call.name if tool_call.name else "unknown_tool"
                tool_arguments = tool_call.arguments if tool_call.arguments else {}
                yield AgentEvent.tool_started(
                        call_id=tool_call.id,
                        tool_name=tool_name,
                        arguments=tool_arguments
                )
                # TODO: when we do config , resolve the path
                result = await self.tool_registry.invoke_tool(tool_name, tool_arguments,Path.cwd())

                yield AgentEvent.tool_finished(
                    call_id=tool_call.id,
                    tool_name=tool_name,
                    result=result
                )

                tool_call_result.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.id,
                        content=result.to_model_output(),
                        is_error=not result.success
                    )
                )

        for tool_result in tool_call_result:
            # add the tool result to the context manager so that it can be used in subsequent tool calls or in the final response if needed
            print(f"Adding tool result to context manager: {tool_result}")
            self.context_manager.add_tool_result(tool_result.tool_call_id, tool_result.content)

    async def _check_for_agent(self) :
        if not self.agentId:
            yield AgentEvent.agent_error(agent_name=self.agentId, message="Agent ID is not set. Please set the agent ID before running the agent.")
        
    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.client:
            await self.client.close()
            self.client = None
