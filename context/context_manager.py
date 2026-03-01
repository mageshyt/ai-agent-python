
from dataclasses import dataclass
from typing import Any
from lib.text import count_tokens
from propmpts.system import get_system_prompt

@dataclass
class MessageItem:
    role: str
    content: str
    token_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result : dict[str, Any] = { "role": self.role }
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

    def add_assistant_message(self, content: str) -> None:
        self._messages.append(MessageItem(role="assistant", content=content, token_count=count_tokens(content, model=self._model)))

    def get_context(self) -> list[dict[str, Any]]:
        context = [{"role": "system", "content": self.system_prompts}]
        for message in self._messages:
            context.append(message.to_dict())
        return context




