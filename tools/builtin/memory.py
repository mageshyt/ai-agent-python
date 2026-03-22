from config.config import Config
from config.loader import get_data_dir
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind
from pydantic import BaseModel, Field
import asyncio
from contextlib import contextmanager
import fcntl
import json
import os
import tempfile

 
class MemoryParams(BaseModel):
    action: str = Field(
        ..., description="Action: 'set', 'get', 'delete', 'list', 'clear'"
    )
    key: str | None = Field(
        None, description="Memory key (required for `set`, `get`, `delete`)"
    )
    value: str | None = Field(None, description="Value to store (required for `set`)")

class MemoryTool(Tool):
    name = "memory"
    description =(
            "Store and retrieve persistent memory"
            "Use this to remember important information across interactions, such as user preferences, session data, or any other relevant details that should persist over time."
    )
    kind = ToolKind.MEMORY
    schema = MemoryParams

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._lock = asyncio.Lock()

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = MemoryParams(**invocation.params)
        action = params.action.lower()

        switcher = {
            "set": self._set_memory,
            "get": self._get_memory,
            "delete": self._delete_memory,
            "list": self._list_memory,
            "clear": self._clear_memory
        }
        func = switcher.get(action)
        if func is None:
            return ToolResult.error_result(
                f"Invalid action: '{params.action}'. Valid actions are 'set', 'get', 'delete', 'list', 'clear'."
            )

        try:
            if action in {"set", "delete", "clear"}:
                async with self._lock:
                    with self._file_lock():
                        return func(params)
            return func(params)
        except Exception as e:
            return ToolResult.error_result(f"Memory operation failed: {str(e)}")


    def _set_memory(self, params: MemoryParams) -> ToolResult:
        if params.key is None or params.value is None:
            return ToolResult.error_result("Both 'key' and 'value' are required for 'set' action.")
        if params.key == "" or params.value == "":
            return ToolResult.error_result("Empty strings are not allowed for 'key' or 'value'.")

            # Load existing memory
        memory = self._load_memory()

        # Update memory with new key-value pair
        memory[params.key] = params.value

        # Save updated memory back to file

        self._save_memory(memory)

        return ToolResult.success_result(
            json.dumps({"action": "set", "key": params.key, "value": params.value}, ensure_ascii=False)
        )
        

    def _get_memory(self, params: MemoryParams) -> ToolResult:
        if params.key is None:
            return ToolResult.error_result("'key' is required for 'get' action.")
        if params.key == "":
            return ToolResult.error_result("Empty string is not allowed for 'key'.")

        memory = self._load_memory()
        value = memory.get(params.key)

        if value is None:
            return ToolResult.error_result(f"No value found for key: '{params.key}'")

        return ToolResult.success_result(
            json.dumps({"action": "get", "key": params.key, "value": value}, ensure_ascii=False)
        )

    def _delete_memory(self, params: MemoryParams) -> ToolResult:
        if params.key is None:
            return ToolResult.error_result("'key' is required for 'delete' action.")
        if params.key == "":
            return ToolResult.error_result("Empty string is not allowed for 'key'.")

        memory = self._load_memory()

        if params.key not in memory:
            return ToolResult.error_result(f"No value found for key: '{params.key}'")

        del memory[params.key]
        self._save_memory(memory)

        return ToolResult.success_result(
            json.dumps({"action": "delete", "key": params.key}, ensure_ascii=False)
        )

    def _list_memory(self, params: MemoryParams) -> ToolResult:
        memory = self._load_memory()

        return ToolResult.success_result(
            json.dumps({"action": "list", "entries": memory}, ensure_ascii=False)
        )


    def _clear_memory(self, params: MemoryParams) -> ToolResult:
        self._save_memory({})
        return ToolResult.success_result(json.dumps({"action": "clear", "entries": {}}, ensure_ascii=False))


    def _load_memory(self) -> dict:
        data_dir = get_data_dir()
        memory_file = data_dir / "user_memory.json"

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

    def _save_memory(self, memory: dict) -> None:
        data_dir = get_data_dir()
        memory_file = data_dir / "user_memory.json"

        if not data_dir.exists():
            data_dir.mkdir(parents=True)

        serialized = json.dumps(memory, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=data_dir, delete=False) as tmp:
            tmp.write(serialized)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = tmp.name

        os.replace(temp_path, memory_file)

    @contextmanager
    def _file_lock(self):
        data_dir = get_data_dir()
        lock_file = data_dir / "user_memory.lock"
        with lock_file.open("a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
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

