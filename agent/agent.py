from __future__ import annotations
import asyncio
from typing import AsyncGenerator

from agent.events import AgentEvent, AgentEventType
from agent.session import Session
from config.config import Config
from lib.response import StreamEventType, TokenUsage, ToolCall, ToolResultMessage
from tools.base import ToolResult


class Agent:
    def __init__(self,config:Config) -> None:
        self.config = config
        self.session:Session = Session(config)
    
    async def run(self, message: str) -> AsyncGenerator[AgentEvent, None]:
        yield AgentEvent.agent_started(agent_name=self.session.agentId , message=message)
        self.session.context_manager.add_user_message(message)
        final_response:str | None = None
        async for event in self._agentic_loop():
            yield event
            if event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content") if event.data.get("content") else "No content"

        yield AgentEvent.agent_finished(agent_name=self.session.agentId , response=final_response, usage=None)


    async def  _agentic_loop(self)->AsyncGenerator[AgentEvent, None]:

        if (not self.session or not self.session.client):
            yield AgentEvent.agent_error(agent_name=self.session.agentId, message="LLM client is not initialized.")
            return
        print("TOKENS USED IN THIS SESSION: ", self.session.context_manager.get_total_usage())
        max_turns = self.config.max_turns if self.config.max_turns else 10
        max_consecutive_tool_failures = max(1, self.config.max_consecutive_tool_failures)
        consecutive_tool_failures = 0
        tools = self.session.tool_registry.get_schemas()
        usage : TokenUsage | None = None

        for _ in range(max_turns):
            self.session.increment_turn()
            response_text = ""

            if self.session.context_manager.is_need_to_reset():
                yield AgentEvent(type=AgentEventType.COMPACTION_STARTED, data={"agent_name": self.session.agentId})
                try:
                    summary, summary_usage = await self.session.chat_compactor.compress(self.session.context_manager)
                    if summary and summary_usage:
                        self.session.context_manager.replace_chat_session(summary)
                        yield AgentEvent(type=AgentEventType.COMPACTION_FINISHED, data={"agent_name": self.session.agentId, "summary": summary, "usage": summary_usage.__dict__})
                    else:
                        yield AgentEvent(type=AgentEventType.COMPACTION_FAILED, data={"agent_name": self.session.agentId, "reason": "Empty summary or usage"})
                except Exception as e:
                    yield AgentEvent(type=AgentEventType.COMPACTION_FAILED, data={"agent_name": self.session.agentId, "reason": str(e)})
            
            message = self.session.context_manager.get_context()
            tool_calls:list[ToolCall] = []
        
            async for event in self.session.client.send_message(message, tools = tools if tools else None, stream=True):
                if event.type == StreamEventType.TEXT_DELTA:
                    content = event.text_delta.content if event.text_delta else ""
                    response_text += content
                    if content:
                        yield AgentEvent.text_delta(agent_name=self.session.agentId, content=content)
                elif event.type == StreamEventType.ERROR:
                    error_message = event.error if event.error else "Unknown error"
                    yield AgentEvent.agent_error(agent_name=self.session.agentId, message=error_message)
                    break

                elif event.type == StreamEventType.TOOL_CALL_END:
                    # we have a complete tool call, now we can execute it
                    if event.tool_call:
                        tool_calls.append(event.tool_call)
                elif event.type == StreamEventType.MESSAGE_COMPLETE:
                        usage = event.usage if event.usage else None
                        
            #NOTE: we will add the assistant message to the context manager after the response is complete, so that we have the full response text available for token counting and other processing if needed. This also allows us to yield a text_complete event with the full response text.
            self.session.context_manager.add_assistant_message(
                response_text,
                [tc.to_dict() for tc in tool_calls] if tool_calls else None,
            )
            
            # Only finalize visible assistant text for non-tool turns.
            if response_text and not tool_calls:
                yield AgentEvent.text_complete(agent_name=self.session.agentId, content=response_text)
 
            if not tool_calls:
                # if there are no tool calls, we can end the agentic loop and return the final response
                if usage:
                    self.session.context_manager.add_usage(usage)

                break
            for tool_call in tool_calls:
                yield AgentEvent.tool_started(
                    call_id=tool_call.id,
                    tool_name=tool_call.name if tool_call.name else "unknown_tool",
                    arguments=tool_call.arguments if tool_call.arguments else {}
                )


            invocation_results = await asyncio.gather(
                *[self._invoke(tc) for tc in tool_calls],
                return_exceptions=True
            )

            tool_call_result: list[ToolResultMessage] = []
            batch_failed_calls = 0
            for tc_orig, item in zip(tool_calls, invocation_results):
                if isinstance(item, BaseException):
                    tool_name = tc_orig.name if tc_orig.name else "unknown_tool"
                    result = ToolResult.error_result(str(item))
                    error_result = ToolResultMessage(
                        tool_call_id=tc_orig.id,
                        content=result.to_model_output(),
                        is_error=True
                    )
                    yield AgentEvent.tool_finished(call_id=tc_orig.id, tool_name=tool_name, result=result)
                    tool_call_result.append(error_result)
                    batch_failed_calls += 1
                    continue
                tc, tool_name, result = item
                yield AgentEvent.tool_finished(call_id=tc.id, tool_name=tool_name, result=result)
                if not result.success:
                    batch_failed_calls += 1
                tool_call_result.append(
                    ToolResultMessage(
                        tool_call_id=tc.id,
                        content=result.to_model_output(),
                        is_error=not result.success
                    )
                )

            for tool_result in tool_call_result:
                self.session.context_manager.add_tool_result(tool_result.tool_call_id, tool_result.content)

            if batch_failed_calls > 0:
                consecutive_tool_failures += batch_failed_calls
            else:
                consecutive_tool_failures = 0

            if consecutive_tool_failures >= max_consecutive_tool_failures:
                yield AgentEvent.agent_error(
                    agent_name=self.session.agentId,
                    message=(
                        "Stopping execution after repeated tool failures "
                        f"({consecutive_tool_failures} consecutive failed tool calls)."
                    ),
                )
                break

    async def _invoke(self,tc: ToolCall):
        name = tc.name if tc.name else "unknown_tool"
        args = tc.arguments if tc.arguments else {}
        result = await self.session.tool_registry.invoke_tool(name, args, self.config.cwd)
        return tc, name, result

    async def __aenter__(self) -> Agent:
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session:
            if self.session.client:
                await self.session.client.close()
            if self.session.mcp_manager:
                await self.session.mcp_manager.shutdown()
            self.session = None
