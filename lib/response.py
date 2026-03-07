from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import json


class StreamEventType(str,Enum):
    TEXT_DELTA = "text_delta"
    MESSAGE_COMPLETE = "message_complete"
    ERROR = "error"

    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"

@dataclass
class TextDelta:
    content: str
    role: str | None = None
    tool_calls: list[dict[str, Any]] | None = None




@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )

@dataclass
class ToolCallDelta:
    id : str
    name : str | None = None
    arguments : str = ""

@dataclass
class ToolCall:
    id : str
    name : str | None = None
    arguments : dict[str, Any] = field(default_factory=dict)
    result : str | None = None
    error : str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
                "id": self.id,
                "type": "function",
                "function": {
                    "name": self.name,
                    "arguments": json.dumps(self.arguments)
                    }
            }

@dataclass
class StreamEvent:
    type : StreamEventType
    tool_call_delta : ToolCallDelta | None = None
    tool_call: ToolCall | None = None
    text_delta: TextDelta | None = None
    error : str | None = None
    finished_reason : str | None = None
    usage : TokenUsage | None = None


def parase_tool_call_arguments(arguments:str) -> dict[str, Any]:
    if not arguments:
        return {}


    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        print("Failed to parse tool call arguments as JSON. Returning raw string.")
        return {"raw_arguments": arguments}


@dataclass
class ToolResultMessage:
    tool_call_id:str
    content:str
    is_error:bool = False

    def to_openai_message(self)->dict[str, Any]:
        return {
            "role": "tool",
            "content": {
                "tool_call_id": self.tool_call_id,
                "result": self.content,
                "is_error": self.is_error
            }
        }
