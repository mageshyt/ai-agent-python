from config.config import Config
from lib import  MAX_FILE,resolve_path, IGNORED_DIRECTORIES
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class GlobParams(BaseModel):
    pattern : str = Field(
            ..., 
            description= 'Glob Pattern to match files against. (e.g. "*.txt" to match all text files, "**/*.py" to match all python files recursively, etc.)',
    )

    path : str = Field(
            ".",
            description= 'File or directory to search in . (default: current directory)',
    )


class GlobTool(Tool):
    name = "glob"
    description = (
            "Search for the files in the specified path that match the given glob pattern."
            "The glob pattern can include wildcards like '*' to match any number of characters, '?' to match a single character, and '**' for recursive search. The tool will return a list of matching file paths."
    )
    kind = ToolKind.READ
    schema = GlobParams


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GlobParams(**invocation.params)

        search_path = resolve_path(invocation.cwd, params.path)
        if not search_path.exists() or not search_path.is_dir():
            return ToolResult.error_result(f"Path '{search_path}' does not exist or is not a directory.")


        try:
            generator = search_path.glob(params.pattern)
            matches = []
            for match in generator:
                if any(ignored in str(match) for ignored in IGNORED_DIRECTORIES):
                    continue
                if match.is_file():
                    matches.append(match)
                    if len(matches) >= MAX_FILE + 1: # fetch one extra to know if we truncated
                        break
        except Exception as e:
            return ToolResult.error_result(f"Error while searching for files: {str(e)}")

        output_matches = []
        for file_path in matches[:MAX_FILE]:  # limit to 1000 files to prevent excessive memory usage
            try :
                relative_path = file_path.relative_to(invocation.cwd)
            except Exception:
                relative_path = file_path

            output_matches.append(str(relative_path))


        if not matches:
            return ToolResult.success_result(f"No matches found for pattern, '{params.pattern}' in path '{search_path}'.")

        if len(matches) >= MAX_FILE:
            output_matches.append(f"Output truncated to {MAX_FILE} files to prevent excessive memory usage.")

        return ToolResult.success_result(
                "\n".join(output_matches),
                metadata={
                    "path": str(search_path),
                    "files_matched": len(matches),
                    "pattern": params.pattern,
                    "truncated": len(matches) >= MAX_FILE
                }
        )


if  __name__ == "__main__":
    import asyncio
    config = Config()
    tool = GlobTool(config)
    invocation = ToolInvocation(
            cwd=resolve_path(".",''), 
            params={
                "pattern": "**/base.py",
                "path": ".",
            }
    )
    result = asyncio.run(tool.execute(invocation))
    print(result.to_model_output())







