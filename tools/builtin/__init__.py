

from tools.base import Tool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.list_dir import  ListDir
from tools.builtin.shell import ShellTool
from tools.builtin.write_file import WriteFile
from tools.builtin.edit_file import EditTool

__all__ = [
    "ReadFileTool",
    "ListDir",
    "ShellTool",
    "WriteFile",
    "EditTool"
]


def get_all_builtin_tools()->list[type]:
    return [
        ReadFileTool,
        ListDir,
        ShellTool,
        WriteFile,
        EditTool
    ]
