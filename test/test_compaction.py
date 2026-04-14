import unittest
from typing import Any

from context.compaction import ChatCompactor
from lib.contants.config import MIN_MESSAGE_LIMIT
from lib.response import StreamEvent, StreamEventType, TextDelta, TokenUsage


class FakeContextManager:
    def __init__(self, messages: list[dict[str, Any]]):
        self._messages = messages

    def get_context(self) -> list[dict[str, Any]]:
        return self._messages


class FakeLLMClient:
    def __init__(self, events: list[StreamEvent] | None = None):
        self._events = events or []
        self.called = False

    async def send_message(self, *_args, **_kwargs):
        self.called = True
        for event in self._events:
            yield event


class TestChatCompactor(unittest.IsolatedAsyncioTestCase):
    async def test_compress_returns_none_below_min_limit(self):
        client = FakeLLMClient()
        compactor = ChatCompactor(client)
        messages = [{"role": "user", "content": "hi"}] * (MIN_MESSAGE_LIMIT - 1)
        context = FakeContextManager(messages)

        summary, usage = await compactor.compress(context)

        self.assertIsNone(summary)
        self.assertIsNone(usage)
        self.assertFalse(client.called)

    def test_compactor_exposes_formatter_method(self):
        compactor = ChatCompactor(FakeLLMClient())
        self.assertTrue(
            hasattr(compactor, "get_formated_messages"),
            "ChatCompactor should expose get_formated_messages as an instance method.",
        )

    async def test_compress_returns_summary_and_usage_when_complete_event_received(self):
        usage = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15, cached_tokens=0)
        events = [
            StreamEvent(
                type=StreamEventType.MESSAGE_COMPLETE,
                text_delta=TextDelta(content="short summary"),
                usage=usage,
            )
        ]
        client = FakeLLMClient(events=events)
        compactor = ChatCompactor(client)

        # Isolate this test from formatter implementation issues so we can
        # validate the compression event-handling path itself.
        compactor.get_formated_messages = lambda _messages: (MIN_MESSAGE_LIMIT, "formatted conversation")

        messages = [{"role": "user", "content": "long enough message for compression"}] * MIN_MESSAGE_LIMIT
        context = FakeContextManager(messages)

        summary, returned_usage = await compactor.compress(context)

        self.assertEqual(summary, "short summary")
        self.assertEqual(returned_usage, usage)
        self.assertTrue(client.called)


if __name__ == "__main__":
    unittest.main()
