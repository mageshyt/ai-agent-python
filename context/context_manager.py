
from dataclasses import dataclass, field
from typing import Any
from lib.text import count_tokens
from propmpts.system import get_system_prompt

@dataclass
class MessageItem:
    role: str
    content: str
    token_count: int | None = None
    tool_call_id : str | None = None
    tool_calls: list[dict[str, Any]] | None = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result : dict[str, Any] = { "role": self.role }

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        if self.tool_calls:
            result["tool_calls"] = self.tool_calls

        if self.content:
            result["content"] = self.content
        if self.token_count is not None:
            result["token_count"] = self.token_count
        return result
class ContextManager:
    def __init__(self) -> None:
        self.system_prompts  = get_system_prompt( )
        self._messages: list[MessageItem] = []
        #TODO: make model configurable
        self._model = "gpt-4"

    def add_user_message(self, content: str) -> None:
        self._messages.append(MessageItem(role="user", content=content , token_count=count_tokens(content, model=self._model)))

    def add_assistant_message(self, content: str,tool_calls:list[dict[str,Any]]) -> None:
        self._messages.append(
                MessageItem(
                    role="assistant", 
                    content=content,
                    token_count=count_tokens(content, model=self._model),
                    tool_calls=tool_calls or []
                    )
                )

    def get_context(self) -> list[dict[str, Any]]:
        context = [{"role": "system", "content": self.system_prompts}]
        for message in self._messages:
            context.append(message.to_dict())
        return context

    def add_tool_result(self, tool_call_id : str , content:str) -> None:
        item= MessageItem(
                role="tool",
                content=content,
                token_count=count_tokens(content, model=self._model),
                tool_call_id=tool_call_id
                )

        self._messages.append(item)




