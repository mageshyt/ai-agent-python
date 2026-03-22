from config.config import Config
from config.loader import get_data_dir
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind
from pydantic import BaseModel, Field
import json

 
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
            return ToolResult.error_result(f"Invalid action: '{params.action}'. Valid actions are 'set', 'get', 'delete', 'list', 'clear'.")

        return func(params)


    def _set_memory(self, params: MemoryParams) -> ToolResult:
        if not params.key or not params.value:
            return ToolResult.error_result("Both 'key' and 'value' are required for 'set' action.")

            # Load existing memory
        memory = self._load_memory()

        # Update memory with new key-value pair
        memory[params.key] = params.value

        # Save updated memory back to file

        self._save_memory(memory)

        return ToolResult.success_result(f"Set memory: '{params.key}' = '{params.value}'")
        

    def _get_memory(self, params: MemoryParams) -> ToolResult:
        if not params.key:
            return ToolResult.error_result("'key' is required for 'get' action.")

        memory = self._load_memory()
        value = memory.get(params.key)

        if value is None:
            return ToolResult.error_result(f"No value found for key: '{params.key}'")

        return ToolResult.success_result(
            f"Value for key '{params.key}': {value}"
        )

    def _delete_memory(self, params: MemoryParams) -> ToolResult:
        if not params.key:
            return ToolResult.error_result("'key' is required for 'delete' action.")

        memory = self._load_memory()

        if params.key not in memory:
            return ToolResult.error_result(f"No value found for key: '{params.key}'")

        del memory[params.key]
        self._save_memory(memory)

        return ToolResult.success_result(f"Deleted key '{params.key}' from memory.")

    def _list_memory(self, params: MemoryParams) -> ToolResult:
        memory = self._load_memory()

        if not memory:
            return ToolResult.success_result("No memory entries found.")

        output = "\n".join(f"{key}: {value}" for key, value in memory.items())
        return ToolResult.success_result(f"Memory entries:\n{output}")


    def _clear_memory(self, params: MemoryParams) -> ToolResult:
        self._save_memory({})
        return ToolResult.success_result("Cleared all memory entries.")


    def _load_memory(self) -> dict:
        data_dir = get_data_dir()
        memory_file = data_dir / "user_memory.json"

        return json.loads(memory_file.read_text()) if memory_file.is_file() else {}

    def _save_memory(self, memory: dict) -> None:
        data_dir = get_data_dir()
        memory_file = data_dir / "user_memory.json"

        if not data_dir.exists():
            data_dir.mkdir(parents=True)

        memory_file.write_text(json.dumps(memory, indent=2, ensure_ascii=False))



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

