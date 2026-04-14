from typing import Any

from context.context_manager import ContextManager
from lib.contants.config import MIN_MESSAGE_LIMIT
from lib.response import StreamEventType, TokenUsage
from llm.client import LLMProvider
from propmpts.system import get_compression_prompt

"""NOTE: For now we are going to build a simple compactor that just remove the oldest and fdaile messages. once we have a complete working version we will start our graph based compactor and pruning  """


class ChatCompactor:
    def __init__(self, client: LLMProvider):
        self.client = client

    async def compress(
        self, context_manager: ContextManager
    ) -> tuple[str | None, TokenUsage | None]:
        messages = context_manager.get_context()

        # if only few messged we dont need to summarize anything
        if len(messages) < MIN_MESSAGE_LIMIT:
            return None, None

        message_count, formatted_message = self.get_formated_messages(messages)

        compression_messages = [
            {"role": "system", "content": get_compression_prompt(message_count)},
            {"role": "user", "content": formatted_message},
        ]
        try:
            summary = ""
            usage = None
            async for event in self.client.send_message(
                compression_messages,
                stream=False,
            ):
                if event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.usage
                    summary += event.text_delta.content or ""

            if not summary or not usage:
                return None, None

            return summary, usage
        except Exception:
            return None, None

def get_formated_messages(self, messages: list[dict[str, Any]]) -> tuple[str, int]:
    output = ["Conversation to summarize:\n"]

    RECENT_WINDOW = 6
    total = len(messages)
    valid_count = 0

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        is_recent = i >= total - RECENT_WINDOW

        if role == "system":
            continue

        # skip low value
        if role == "user" and len(content.strip()) < 10:
            continue
        
        valid_count += 1
        limit = 3000 if is_recent else 800

        if role == "tool":
            tool_id = msg.get("tool_call_id", "unknown")
            truncated = content[:limit]

            if len(content) > limit:
                truncated += "\n...[truncated]"

            output.append(f"[Tool Result: {tool_id}]\n{truncated}")

        elif role == "assistant":
            if content:
                truncated = content[:limit]
                if len(content) > limit:
                    truncated += "\n...[truncated]"

                output.append(f"[Assistant]\n{truncated}")

            if msg.get("tool_calls"):
                tool_details = []
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name", "unknown")
                    args = func.get("arguments", "{}")[:300]

                    tool_details.append(f"- {name}({args})")

                output.append("[Assistant Tool Calls]\n" + "\n".join(tool_details))

        else:
            truncated = content[:limit]
            if len(content) > limit:
                truncated += "\n...[truncated]"

            output.append(f"[User]\n{truncated}")

    return ("\n\n---\n\n".join(output), valid_count)