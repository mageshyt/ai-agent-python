

from tools.base import Tool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.list_dir import  ListDir
from tools.builtin.shell import ShellTool

__all__ = [
    "ReadFileTool",
    "ListDir"
    "ShellTool"
]


def get_all_builtin_tools()->list[type[Tool]]:
    return [
        ReadFileTool,
        ListDir,
        ShellTool
    ]
