from config.config import Config
import uuid
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind
from pydantic import BaseModel, Field


class TodoParams(BaseModel):
    action: str = Field(..., description="The action to perform on the todo list. Can be 'add', 'remove', 'clear' or 'list'.")
    id: str = Field(None, description="The ID of the todo item (for complete,remove).")
    content: str = Field(None, description="The content of the todo item (for add).")



class TodoTool(Tool):
    name = "todos"
    description = (
        "Manage a simple todo list"
        "You can add, remove, or list todo items. Each item has a unique ID and content."
        "Use 'add' action to add a new item with content, 'remove' action to remove an item by ID, and 'list' action to see all current items."
        "'complete' action can be used to mark an item as completed by ID."
        "clear' action can be used to remove all items from the list."
        "NOTE: Must use this tool to manage large and complex tasks, as it provides a persistent in-memory store for todo items. "
        "The tool maintains an in-memory list of todo items that persists across invocations, but will be lost if the tool is restarted."
        
    )

    kind = ToolKind.MEMORY
    schema = TodoParams


    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.todos = {}


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TodoParams(**invocation.params)

        action = params.action.lower()

        switcher = {
            "add": self._add_todo,
            "remove": self._remove_todo,
            "list": self._list_todos,
            "complete": self._complete_todo,
            'clear': self._clear_todos
        }

        func = switcher.get(action)
        if func is None:
            return ToolResult.error_result(f"Invalid action: '{params.action}'. Valid actions are 'add', 'remove', 'list', 'complete'.")

        return func(params)



    def _add_todo(self, params: TodoParams) -> ToolResult:
        if not params.content:
            return ToolResult.error_result("Content is required to add a todo item.")

        todo_id = str(uuid.uuid4())
        self.todos[todo_id] = {"content": params.content, "completed": False}
        return ToolResult.success_result(f"Added todo item with ID: {todo_id}")


    def _remove_todo(self, params: TodoParams) -> ToolResult:
        if not params.id:
            return ToolResult.error_result("ID is required to remove a todo item.")

        if params.id not in self.todos:
            return ToolResult.error_result(f"No todo item found with ID: {params.id}")

        del self.todos[params.id]
        return ToolResult.success_result(f"Removed todo item with ID: {params.id}")

    def _list_todos(self, params: TodoParams) -> ToolResult:
        if not self.todos:
            return ToolResult.success_result("No todo items found.")

        output = []
        for todo_id, todo in self.todos.items():
            status = "✓" if todo["completed"] else "✗"
            output.append(f"{status} [{todo_id}] {todo['content']}")

        return ToolResult.success_result("\n".join(output))

    def _complete_todo(self, params: TodoParams) -> ToolResult:
        if not params.id:
            return ToolResult.error_result("ID is required to complete a todo item.")

        if params.id not in self.todos:
            return ToolResult.error_result(f"No todo item found with ID: {params.id}")

        self.todos[params.id]["completed"] = True
        return ToolResult.success_result(f"Marked todo item with ID: {params.id} as completed.")

    def _clear_todos(self, params: TodoParams) -> ToolResult:
        self.todos.clear()
        return ToolResult.success_result("Cleared all todo items.")
