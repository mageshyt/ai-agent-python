

from tools.base import Tool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.list_dir import ListDir
from tools.builtin.shell import ShellTool
from tools.builtin.write_file import WriteFile
from tools.builtin.edit_file import EditTool
from tools.builtin.docker_tool import DockerTool

__all__ = [
    "ReadFileTool",
    "ListDir",
    "ShellTool",
    "WriteFile",
    "EditTool",
    "DockerTool"
]


def get_all_builtin_tools()->list[type]:
    return [
        DockerTool,
        ReadFileTool,
        ListDir,
        WriteFile,
        EditTool,
        ShellTool,
    ]
