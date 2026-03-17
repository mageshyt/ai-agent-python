from tools.base import Tool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.list_dir import  ListDirTool
from tools.builtin.shell import ShellTool
from tools.builtin.write_file import WriteFile
from tools.builtin.edit_file import EditTool
from tools.builtin.grep import GrepTool

__all__ = [
    "ReadFileTool",
    "ListDirTool",
    "ShellTool",
    "WriteFile",
    "EditTool",
    "GrepTool"
]


def get_all_builtin_tools()->list[type]:
    return [
        ReadFileTool,
        ListDirTool,
        WriteFile,
        EditTool,
        GrepTool,
        ShellTool,
    ]
