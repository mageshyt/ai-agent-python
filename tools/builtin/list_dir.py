from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from lib import resolve_path


class ListDirParams(BaseModel):
    path: str = Field(
        ".",
        description="The directory path to list (default: current directory)",
    )
    include_hidden: bool = Field(
        False,
        description="Whether to include hidden files and directories (default: False)",
    )

    recursive: bool = Field(
        False,
        description="Whether to list directories recursively (default: False)",
    )


class ListDir(Tool):
    name = "list_dir"
    description = "List the contents of a directory"
    kind = ToolKind.FILE_SYSTEM
    schema = ListDirParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ListDirParams(**invocation.params)
        dir_path = resolve_path(invocation.cwd, params.path)

        if not dir_path.exists() or not dir_path.is_dir():
            return ToolResult.error_result(f"Directory not found: {dir_path}")

        try:
            items = sorted(dir_path.iterdir(), key=lambda p: p.name.lower())
        except Exception as e:
            return ToolResult.error_result(f"Error listing directory: {e}")

        if not params.include_hidden:
            items = [item for item in items if not item.name.startswith(".")] # filter out hidden files

        if not items:
            return ToolResult.success_result("Directory is empty")

        list_output = ""
        if params.recursive:
            for item in items:
                if item.is_dir():
                    list_output += f"{item.name}/\n"
                    try:
                        sub_items = sorted(item.iterdir(), key=lambda p: p.name.lower())
                        if not params.include_hidden:
                            sub_items = [sub_item for sub_item in sub_items if not sub_item.name.startswith(".")]
                        for sub_item in sub_items:
                            list_output += f"  {sub_item.name}/\n" if sub_item.is_dir() else f"  {sub_item.name}\n"
                    except Exception as e:
                        list_output += f"  [Error listing contents: {e}]\n"
                else:
                    list_output += f"{item.name}\n"
        else:
            list_output = "\n".join(f"{item.name}/" if item.is_dir() else item.name for item in items)

        return ToolResult.success_result(
                list_output,
                metadata={
                    "path": str(dir_path),
                    "num_items": len(items),
                    "entries": [
                        {
                            "name": item.name,
                            "is_dir": item.is_dir(),
                            "size": item.stat().st_size,
                            "modified_time": item.stat().st_mtime
                        } for item in items
                    ]
                    }
                )


if __name__ == "__main__":
    import asyncio
    config = Config()
    tool = ListDir(config)
    invocation = ToolInvocation(cwd=resolve_path(".",''), params={"path": ".", "include_hidden": False, "recursive": True})
    result = asyncio.run(tool.execute(invocation))
    print(result.to_model_output())
