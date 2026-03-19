__all__ = ["get_all_builtin_tools"]






def get_all_builtin_tools() -> list[type]:
    from tools.builtin.web_search import WebSearchTool
    from tools.builtin.edit_file import EditTool
    from tools.builtin.glob import GlobTool
    from tools.builtin.grep import GrepTool
    from tools.builtin.list_dir import ListDirTool
    from tools.builtin.read_file import ReadFileTool
    from tools.builtin.shell import ShellTool
    from tools.builtin.web_scrap import WebScrapTool
    from tools.builtin.write_file import WriteFile
    from tools.builtin.todo import TodoTool

    return [
        ReadFileTool,
        ListDirTool,
        WriteFile,
        EditTool,
        GrepTool,
        ShellTool,
        GlobTool,
        WebSearchTool,
        WebScrapTool,
        TodoTool
    ]
