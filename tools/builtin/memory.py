from config.config import Config
from config.loader import get_data_dir
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind
from pydantic import BaseModel, Field
from typing import Literal
import asyncio
from contextlib import contextmanager
import fcntl
import json
import os
import tempfile
import time

 
class MemoryParams(BaseModel):
    action: str = Field(
        ..., description="Action: 'set', 'get', 'delete', 'list', 'clear', 'sweep'"
    )
    scope: Literal["short", "long", "all"] = Field(
        "long",
        description="Memory scope. Use 'short' for short-term memory, 'long' for persistent memory. 'all' is allowed only for 'list' and 'clear'.",
    )
    key: str | None = Field(
        None, description="Memory key (required for `set`, `get`, `delete`)"
    )
    value: str | None = Field(None, description="Value to store (required for `set`)")
    ttl_seconds: int | None = Field(
        None,
        ge=1,
        description="Optional TTL in seconds. Supported only for scope='short' with action='set'.",
    )


class MemoryTool(Tool):
    name = "memory"
    description = (
            "Store and retrieve scoped memory. "
            "Use scope='long' for persistent memory and scope='short' for short-term memory. "
            "For list, clear, and sweep actions, scope='all' is also supported."
    )
    kind = ToolKind.MEMORY
    schema = MemoryParams

    SCOPE_TO_FILE = {
        "long": "user_memory.json",
        "short": "short_term_memory.json",
    }

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._lock = asyncio.Lock()

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)
        action = params.action.lower()
        scope = params.scope.lower()

        switcher = {
            "set": self._set_memory,
            "get": self._get_memory,
            "delete": self._delete_memory,
            "list": self._list_memory,
            "clear": self._clear_memory,
            "sweep": self._sweep_memory,
        }
        func = switcher.get(action)
        if func is None:
            return ToolResult.error_result(
                f"Invalid action: '{params.action}'. Valid actions are 'set', 'get', 'delete', 'list', 'clear', 'sweep'."
            )

        if scope == "all" and action in {"set", "get", "delete"}:
            return ToolResult.error_result("scope='all' is only allowed for 'list' and 'clear' actions.")

        if params.ttl_seconds is not None and not (action == "set" and scope == "short"):
            return ToolResult.error_result("'ttl_seconds' is only supported for action='set' with scope='short'.")

        try:
            if action in {"set", "delete", "clear", "sweep"}:
                async with self._lock:
                    with self._file_lock():
                        return func(params, scope)
            return func(params, scope)
        except Exception as e:
            return ToolResult.error_result(f"Memory operation failed: {str(e)}")


    def _set_memory(self, params: MemoryParams, scope: str) -> ToolResult:
        if params.key is None or params.value is None:
            return ToolResult.error_result("Both 'key' and 'value' are required for 'set' action.")
        if params.key == "" or params.value == "":
            return ToolResult.error_result("Empty strings are not allowed for 'key' or 'value'.")

        memory = self._load_memory(scope)

        if scope == "short":
            memory = self._active_short_memory(memory)
            expires_at = time.time() + params.ttl_seconds if params.ttl_seconds is not None else None
            memory[params.key] = {"value": params.value, "expires_at": expires_at}
        else:
            memory[params.key] = params.value
            expires_at = None

        self._save_memory(scope, memory)

        return ToolResult.success_result(
            json.dumps(
                {
                    "action": "set",
                    "scope": scope,
                    "key": params.key,
                    "value": params.value,
                    "ttl_seconds": params.ttl_seconds if scope == "short" else None,
                    "expires_at": expires_at,
                },
                ensure_ascii=False,
            )
        )
        

    def _get_memory(self, params: MemoryParams, scope: str) -> ToolResult:
        if params.key is None:
            return ToolResult.error_result("'key' is required for 'get' action.")
        if params.key == "":
            return ToolResult.error_result("Empty string is not allowed for 'key'.")

        memory = self._load_memory(scope)

        if scope == "short":
            memory = self._active_short_memory(memory)
            value, expires_at = self._decode_short_entry(memory.get(params.key))
        else:
            value = memory.get(params.key)
            expires_at = None

        if value is None:
            return ToolResult.error_result(f"No value found for key: '{params.key}'")

        return ToolResult.success_result(
            json.dumps(
                {"action": "get", "scope": scope, "key": params.key, "value": value, "expires_at": expires_at},
                ensure_ascii=False,
            )
        )

    def _delete_memory(self, params: MemoryParams, scope: str) -> ToolResult:
        if params.key is None:
            return ToolResult.error_result("'key' is required for 'delete' action.")
        if params.key == "":
            return ToolResult.error_result("Empty string is not allowed for 'key'.")

        memory = self._load_memory(scope)

        if scope == "short":
            memory = self._active_short_memory(memory)

        if params.key not in memory:
            return ToolResult.error_result(f"No value found for key: '{params.key}'")

        del memory[params.key]
        self._save_memory(scope, memory)

        return ToolResult.success_result(
            json.dumps({"action": "delete", "scope": scope, "key": params.key}, ensure_ascii=False)
        )

    def _list_memory(self, params: MemoryParams, scope: str) -> ToolResult:
        if scope == "all":
            entries = {
                "long": self._load_memory("long"),
                "short": self._short_entries_for_output(self._active_short_memory(self._load_memory("short"))),
            }
        elif scope == "short":
            entries = self._short_entries_for_output(self._active_short_memory(self._load_memory("short")))
        else:
            entries = self._load_memory(scope)

        return ToolResult.success_result(
            json.dumps({"action": "list", "scope": scope, "entries": entries}, ensure_ascii=False)
        )


    def _clear_memory(self, params: MemoryParams, scope: str) -> ToolResult:
        if scope == "all":
            self._save_memory("long", {})
            self._save_memory("short", {})
            return ToolResult.success_result(
                json.dumps({"action": "clear", "scope": "all", "entries": {"long": {}, "short": {}}}, ensure_ascii=False)
            )

        self._save_memory(scope, {})
        return ToolResult.success_result(json.dumps({"action": "clear", "scope": scope, "entries": {}}, ensure_ascii=False))

    def _sweep_memory(self, params: MemoryParams, scope: str) -> ToolResult:
        if scope == "long":
            return ToolResult.success_result(
                json.dumps(
                    {"action": "sweep", "scope": "long", "expired_removed": 0, "note": "Long-term memory has no TTL sweep."},
                    ensure_ascii=False,
                )
            )

        if scope == "all":
            short_memory = self._load_memory("short")
            cleaned_short, removed = self._prune_short_memory(short_memory)
            self._save_memory("short", cleaned_short)
            return ToolResult.success_result(
                json.dumps(
                    {
                        "action": "sweep",
                        "scope": "all",
                        "expired_removed": {"short": removed, "long": 0},
                    },
                    ensure_ascii=False,
                )
            )

        short_memory = self._load_memory("short")
        cleaned_short, removed = self._prune_short_memory(short_memory)
        self._save_memory("short", cleaned_short)
        return ToolResult.success_result(
            json.dumps(
                {"action": "sweep", "scope": "short", "expired_removed": removed},
                ensure_ascii=False,
            )
        )

    def _active_short_memory(self, memory: dict) -> dict:
        active, _ = self._prune_short_memory(memory)
        return active

    def _prune_short_memory(self, memory: dict) -> tuple[dict, int]:
        now = time.time()
        active: dict = {}
        removed = 0

        for key, raw_entry in memory.items():
            value, expires_at = self._decode_short_entry(raw_entry)
            if value is None:
                removed += 1
                continue
            if expires_at is not None and expires_at <= now:
                removed += 1
                continue
            active[key] = {"value": value, "expires_at": expires_at}

        return active, removed

    def _short_entries_for_output(self, memory: dict) -> dict:
        output: dict = {}
        for key, raw_entry in memory.items():
            value, expires_at = self._decode_short_entry(raw_entry)
            if value is None:
                continue
            output[key] = {"value": value, "expires_at": expires_at}
        return output

    def _decode_short_entry(self, entry):
        if entry is None:
            return None, None
        if isinstance(entry, dict):
            value = entry.get("value")
            expires_at = entry.get("expires_at")
            if value is None:
                return None, None
            if expires_at is not None:
                try:
                    expires_at = float(expires_at)
                except (TypeError, ValueError):
                    expires_at = None
            return value, expires_at
        return entry, None


    def _load_memory(self, scope: str) -> dict:
        memory_file = self._get_memory_file(scope)

        if not memory_file.is_file():
            return {}

        try:
            content = memory_file.read_text(encoding="utf-8")
            if not content.strip():
                return {}
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Memory file is not valid JSON: {memory_file}. {str(e)}") from e
        except OSError as e:
            raise ValueError(f"Failed to read memory file: {memory_file}. {str(e)}") from e

        if not isinstance(data, dict):
            raise ValueError(f"Memory file must contain a JSON object at top level: {memory_file}")

        return data

    def _save_memory(self, scope: str, memory: dict) -> None:
        data_dir = get_data_dir()
        memory_file = self._get_memory_file(scope)

        if not data_dir.exists():
            data_dir.mkdir(parents=True)

        serialized = json.dumps(memory, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=data_dir, delete=False) as tmp:
            tmp.write(serialized)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = tmp.name

        os.replace(temp_path, memory_file)

    def _get_memory_file(self, scope: str):
        file_name = self.SCOPE_TO_FILE.get(scope)
        if file_name is None:
            raise ValueError(f"Invalid scope: '{scope}'. Valid scopes are 'short', 'long', 'all'.")
        return get_data_dir() / file_name

    @contextmanager
    def _file_lock(self):
        data_dir = get_data_dir()
        lock_file = data_dir / "user_memory.lock"
        with lock_file.open("a+") as lock_handle:
            # lock the file for exclusive access, creating it if it doesn't exist
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                # release the lock
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN) 



if __name__ == "__main__":
    config = Config()
    import asyncio

    memory_tool = MemoryTool(config)

    result = memory_tool.execute(ToolInvocation(cwd = ".",params={"action": "set", "key": "favorite_color", "value": "blue"}))
    print(asyncio.run(result))

    result = memory_tool.execute(ToolInvocation(cwd = ".",params={"action": "get", "key": "favorite_color"}))
    print(asyncio.run(result))


    result = memory_tool.execute(ToolInvocation(cwd = ".",params={"action": "list"}))
    print(asyncio.run(result))

