import os
from pathlib import Path
import re
from config.config import Config
from lib import IGNORED_DIRECTORIES, MAX_FILE, is_binary_file
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from lib import resolve_path

class GrepParams(BaseModel):
    pattern : str = Field(
            ..., 
            description= 'Regular expression pattern to search for'
    )

    path : str = Field(
            ... ,
            description= 'File or directory to search in . (default: current directory)',
    )

    case_sensitive : bool = Field(
            False,
            description= 'Whether the search should be case-sensitive (default: False)',
    )


class GrepTool(Tool):
    name = "grep"
    description = (
            "Search for a pattern in files using the grep command. "
            "You can specify the pattern, the file or directory to search in, whether the search should be case-sensitive, and any additional options for the grep command."
    )
    kind = ToolKind.READ
    schema = GrepParams


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = GrepParams(**invocation.params)

        path = resolve_path(invocation.cwd, params.path)
        if not path.exists():
            return ToolResult.error_result(f"Path '{path}' does not exist.")

        case_flag = re.IGNORECASE if not params.case_sensitive else 0

        try:
            pattern = re.compile(params.pattern,case_flag)
        except re.error as e:
            return ToolResult.error_result(f"Invalid regular expression pattern: {e}")


        if path.is_dir():
            files = self._find_files(path)

        else:
            files = [path]

        #NOTE: this is not the most efficient way to search for patterns in files, but it allows us to avoid potential security issues with running shell commands and gives us more control over the search process. For large files or directories, a more efficient approach would be needed.

        matches = []
        files_matched = 0
        for file in files:
            try:
                content = file.read_text(errors='ignore', encoding='utf-8')
            except Exception as e:
                continue
            lines = content.splitlines()
            is_file_matched = False

            for idx, line in enumerate(lines):
                if pattern.search(line):
                    if not is_file_matched:
                        is_file_matched = True
                        files_matched += 1
                    relative_path = file.relative_to(invocation.cwd)
                    matches.append(f"{relative_path}:{idx+1}:{line}")
                    
            if is_file_matched:
                matches.append("")

        if not matches:
            return ToolResult.success_result(f"No matches found for pattern, '{params.pattern}' in path '{path}'.")

        if len(matches) >= MAX_FILE:
            matches.append(f"Output truncated to {MAX_FILE} matches to prevent excessive memory usage.")

        return ToolResult.success_result(
                "\n".join(matches),
                metadata={
                    "path": str(path),
                    "files_searched": len(files),
                    "files_matched": files_matched,
                    "matches" : matches,
                    "pattern": params.pattern,
                    "truncated": len(matches) >= MAX_FILE
                }
        )



    def _find_files(self, directory)->list[Path]:
        files = []
        for root, _ , filenames in os.walk(directory):
            if any(ignored in root for ignored in IGNORED_DIRECTORIES):
                continue
            for filename in filenames:
                if filename.startswith('.'):
                    continue

                # only read text files
                file_path = Path(root) / filename
                if not is_binary_file(file_path):
                    files.append(file_path)
                    if len(files) >= MAX_FILE:  # limit to 1000 files to prevent excessive memory usage
                        return files

        return files

if  __name__ == "__main__":
    import asyncio
    config = Config()
    tool = GrepTool(config)
    invocation = ToolInvocation(
            cwd=resolve_path(".",''), 
            params={
                "pattern": "TODO",
                "path": ".",
                "case_sensitive": False,
                "additional_options": "-r"
            }
    )
    result = asyncio.run(tool.execute(invocation))
    print(result.to_model_output())







