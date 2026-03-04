import asyncio
import logging
import dotenv
from lib.response import StreamEventType, StreamEvent, TextDelta, TokenUsage, ToolCall, ToolCallDelta, parase_tool_call_arguments
from openai import AsyncOpenAI , RateLimitError, APIConnectionError
from typing import Any, AsyncGenerator

dotenv.load_dotenv()

class LLMProvider:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self.model: str = "arcee-ai/trinity-large-preview:free"  # default model, can be overridden by passing a different model name to the constructor
        self.max_retries: int = 3  # maximum number of retries for rate limit errors

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=dotenv.get_key(dotenv.find_dotenv(), "API_KEY"),
                base_url=dotenv.get_key(dotenv.find_dotenv(), "BASE_URL"),
            )
        return self._client
    
    def _build_tools(self,tools: list[dict[str,Any]]):
        return [ 
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {
                            "type": "object",
                            "properties": {},
                            })
                        }
                    } for tool in tools
                ]
    async def send_message(
        self, message: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True
        ) -> AsyncGenerator[StreamEvent, None]:

        client = self.get_client()
        kwargs = {"model": self.model, "messages": message, "stream": stream}

        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"  # let the model decide which tool to use, we can also implement a more complex tool selection strategy if needed

        for attempt in range(self.max_retries+1):
            try :

                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event
                return
            except RateLimitError as e:
                if attempt < self.max_retries:
                    # backoff strategy: wait for a short period before retrying, you can implement exponential backoff if desired
                    await asyncio.sleep(2 ** attempt)  # simple exponential backoff
                    continue
                else:
                    yield StreamEvent(type=StreamEventType.ERROR, error="Rate limit exceeded. Please try again later.")
                    return
            except APIConnectionError as e:
                yield StreamEvent(type=StreamEventType.ERROR, error=f"API connection error: {str(e)}. Please check your network connection and try again.")
                return
            except Exception as e:
                yield StreamEvent(type=StreamEventType.ERROR, error=str(e))
                return

    async def _stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
        ) -> AsyncGenerator[StreamEvent, None]:

        resposne = await client.chat.completions.create(**kwargs)
        usage : TokenUsage | None = None
        finished_reason : str | None = None
        tool_calls:dict[int, dict[str, Any]] = {}

        async for chunk in resposne:

            # if the chunk contains usage information, we can extract it and include it in the StreamEvent
            if hasattr(chunk, "usage") and chunk.usage is not None:
                usage = TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                    cached_tokens=chunk.usage.prompt_tokens_details.cached_tokens,
                )

            if not hasattr(chunk, "choices") or len(chunk.choices) == 0:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            text_delta = None

            if delta.tool_calls:
                for idx, tool_call in enumerate(delta.tool_calls):
                    print(f"Tool call delta received: {tool_call}")
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            'id' : tool_call.id if hasattr(tool_call, "id") else "",
                            "name": '',
                            'arguments': ''
                        }

                        if tool_call.function:
                            if tool_call.function.name:
                                tool_calls[idx]["name"] = tool_call.function.name
                                yield StreamEvent(
                                        type = StreamEventType.TOOL_CALL_START,
                                        tool_call_delta= ToolCallDelta(
                                            id=tool_calls[idx]['id'],
                                            name=tool_calls[idx]['name'],
                                            arguments=tool_calls[idx]['arguments']
                                            )
                                        )


                            if hasattr(tool_call.function,"arguments"):
                                tool_calls[idx]['arguments'] += tool_call.function.arguments
                                yield StreamEvent(
                                    type = StreamEventType.TOOL_CALL_DELTA,
                                    tool_call_delta= ToolCallDelta(
                                        id=tool_calls[idx]['id'],
                                        name=tool_calls[idx]['name'],
                                        arguments=tool_calls[idx]['arguments']
                                        )
                                    )
            if delta.content is not None:
                text_delta = TextDelta(content=delta.content, role=delta.role)

                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    text_delta=text_delta,
                )
        for idx, tool_call in tool_calls.items():
            yield StreamEvent(
                    type = StreamEventType.TOOL_CALL_END,
                    tool_call = ToolCall(
                        id=tool_call['id'],
                        name = tool_call['name'],
                        arguments = parase_tool_call_arguments(tool_call['arguments']),
                    )
                )
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            finished_reason=finished_reason,
            usage=usage
        )

    async def _non_stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
    ) -> StreamEvent:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message


        text_delta = None
        usage = None

        if message.content is not None:
            text_delta = TextDelta(content=message.content, role=message.role)

        tool_calls:[ToolCall] = []
        if message.tool_calls:
            for idx, tool_call in enumerate(message.tool_calls):
                tool_calls.append(ToolCall(
                    id=tool_call.id if hasattr(tool_call, "id") else "",
                    name=tool_call.function.name if hasattr(tool_call, "function") and hasattr(tool_call.function,"name") else "",
                    arguments=parase_tool_call_arguments(tool_call.function.arguments) if hasattr(tool_call, "function") and hasattr(tool_call.function,"arguments") else "",
                ))

        if response.usage is not None:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens,
            )




        return StreamEvent(
            type=StreamEventType.TEXT_DELTA,
            text_delta=text_delta,
            finished_reason=choice.finish_reason,
            usage=usage
        )


    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    def change_model(self, model_name: str) -> None:
        self.model = model_name

