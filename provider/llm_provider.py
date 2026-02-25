import dotenv
from lib.response import EventType, StreamEvent, TextDelta, TokenUsage
from openai import AsyncOpenAI
from typing import Any, AsyncGenerator

dotenv.load_dotenv()


class LLMProvider:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None
        self.model: str = "arcee-ai/trinity-large-preview:free"  # default model, can be overridden by passing a different model name to the constructor

    def get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=dotenv.get_key(dotenv.find_dotenv(), "API_KEY"),
                base_url=dotenv.get_key(dotenv.find_dotenv(), "BASE_URL"),
            )
        return self._client

    async def send_message(
        self, message: list[dict[str, any]], stream: bool = True
        ) -> AsyncGenerator[StreamEvent, None]:
        client = self.get_client()
        kwargs = {"model": self.model, "messages": message, "stream": stream}

        if stream:
            async for event in self._stream_response(client, kwargs):
                yield event
        else:
            event = await self._non_stream_response(client, kwargs)
            yield event

    async def _stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
        ) -> AsyncGenerator[StreamEvent, None]:

        resposne = await client.chat.completions.create(**kwargs)
        usage : TokenUsage | None = None
        finished_reason : str | None = None

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
            message = choice.delta

            text_delta = None

            if hasattr(choice, "finish_reason") and choice.finish_reason is not None:
                finished_reason = choice.finish_reason

            if message.content is not None:
                text_delta = TextDelta(content=message.content, role=message.role)

                yield StreamEvent(
                    type=EventType.TEXT_DELTA,
                    text_delta=text_delta,
                )

        yield StreamEvent(
            type=EventType.MESSAGE_COMPLETE,
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

        if response.usage is not None:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                cached_tokens=response.usage.prompt_tokens_details.cached_tokens,
            )

        return StreamEvent(
            type=EventType.TEXT_DELTA,
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

