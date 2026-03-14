from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from lib import resolve_path
from lib.constants import IGNORED_DIRECTORIES


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

        def build_tree(current_path, include_hidden, recursive, prefix="") -> str:
            try:
                paths = sorted(current_path.iterdir(), key=lambda p: p.name.lower())
            except Exception as e:
                return f"{prefix}└── [Error reading directory: {e}]\n"

            if not include_hidden:
                paths = [p for p in paths if not p.name.startswith(".")]

            tree_out = ""
            for index, item in enumerate(paths):
                is_last = index == len(paths) - 1
                if item.name in IGNORED_DIRECTORIES:
                    connector = "└── " if is_last else "├── "
                    tree_out += f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''} [ignored]\n"
                    continue

                connector = "└── " if is_last else "├── "
                
                tree_out += f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}\n"
                
                if item.is_dir() and recursive:
                    extension = "    " if is_last else "│   "
                    tree_out += build_tree(item, include_hidden, recursive, prefix + extension)
            
            return tree_out

        list_output = f"{dir_path.name}/\n" + build_tree(dir_path, params.include_hidden, params.recursive)

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
