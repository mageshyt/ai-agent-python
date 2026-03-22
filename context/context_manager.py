
from dataclasses import dataclass, field
from typing import Any
from config.config import Config
from config.loader import get_data_dir
from lib.text import count_tokens
from propmpts.system import get_system_prompt
from tools.base import Tool
import json
import time

@dataclass
class MessageItem:
    role: str
    content: str
    token_count: int | None = None
    tool_call_id : str | None = None
    tool_calls: list[dict[str, Any]] | None = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role}

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        if self.tool_calls:
            result["tool_calls"] = self.tool_calls

        # Some providers require assistant messages to include content even when
        # the turn only contains tool_calls (empty string content).
        if self.role in {"assistant", "tool"} or self.content:
            result["content"] = self.content

        return result
class ContextManager:
    def __init__(self,config:Config,tools:list[Tool]) -> None:
        self.system_prompts  = get_system_prompt(
                config,
                self._load_memory(),
                tools
                )
        self._messages: list[MessageItem] = []
        self._config = config
        self._model = config.get_model_name


    def add_user_message(self, content: str) -> None:
        self._messages.append(MessageItem(role="user", content=content , token_count=count_tokens(content )))

    def add_assistant_message(self, content: str,tool_calls:list[dict[str,Any]] | None) -> None:
        self._messages.append(
                MessageItem(
                    role="assistant", 
                    content=content,
                    token_count=count_tokens(content),
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
                token_count=count_tokens(content),
                tool_call_id=tool_call_id
                )

        self._messages.append(item)


    def _load_memory(self) -> str | None:
        data_dir = get_data_dir()
        long_memory_file = data_dir / "user_memory.json"
        short_memory_file = data_dir / "short_term_memory.json"

        long_entries: dict[str, Any] = {}
        short_entries: dict[str, Any] = {}

        if long_memory_file.is_file():
            try:
                raw_long = long_memory_file.read_text(encoding="utf-8")
                parsed_long = json.loads(raw_long) if raw_long.strip() else {}
                if isinstance(parsed_long, dict):
                    long_entries = parsed_long
            except (OSError, ValueError, json.JSONDecodeError):
                long_entries = {}

        if short_memory_file.is_file():
            try:
                raw_short = short_memory_file.read_text(encoding="utf-8")
                parsed_short = json.loads(raw_short) if raw_short.strip() else {}
                if isinstance(parsed_short, dict):
                    now = time.time()
                    for key, raw_entry in parsed_short.items():
                        if isinstance(raw_entry, dict):
                            value = raw_entry.get("value")
                            expires_at = raw_entry.get("expires_at")
                            if value is None:
                                continue
                            if expires_at is not None:
                                try:
                                    expires_at = float(expires_at)
                                except (TypeError, ValueError):
                                    expires_at = None
                            if expires_at is not None and expires_at <= now:
                                continue
                            short_entries[key] = {"value": value, "expires_at": expires_at}
                        else:
                            short_entries[key] = {"value": raw_entry, "expires_at": None}
            except (OSError, ValueError, json.JSONDecodeError):
                short_entries = {}

        if not long_entries and not short_entries:
            return None

        return json.dumps(
            {
                "long": long_entries,
                "short": short_entries,
            },
            ensure_ascii=False,
            indent=2,
        )

