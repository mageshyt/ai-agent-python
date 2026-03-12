
from pydantic import BaseModel, Field
from lib.paths import ensure_parent_directory
from tools.base import FileDiff, Tool, ToolInvocation, ToolKind, ToolResult
from lib import resolve_path


class WriteFileParams(BaseModel):
    path : str = Field(
            ...,
            description="The path to the file to write to. Can be an absolute or relative path. If the file does not exist, it will be created. If it does exist, it will be overwritten."
    )
    content : str = Field(
            ...,
            description="The content to write to the file."
    )

    create_directories : bool = Field(
            True,
            description="Whether to create parent directories if they do not exist. Defaults to True."
    )





class WriteFile(Tool):
    name = "write_file"
    description = (
        "Write content to a file. Creates the file if it doesn't exist, "
        "or overwrites if it does. Parent directories are created automatically. "
        "Use this for creating new files or completely replacing file contents. "
        "For partial modifications, use the edit tool instead."
    )

    kind = ToolKind.WRITE
    schema = WriteFileParams



    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = WriteFileParams(**invocation.params)

        path = resolve_path(invocation.cwd, params.path)

        is_new_file = not path.exists()
        existing_content = ""

        if not is_new_file:
            # read the existing content so we can include it in the result
            try:
                existing_content = path.read_text(encoding="utf-8")
            except Exception as e:
                pass


        try :
            if params.create_directories:
                ensure_parent_directory(path)
            elif not path.parent.exists():
                return ToolResult.error_result(f"Parent directory does not exist for path: {path}")

            path.write_text(params.content, encoding="utf-8")


            # we need to format the result
            action = "created" if is_new_file else "overwritten"

            total_lines =len(params.content.splitlines())
            result_content = f"File {action} at path: {path}. Total lines written: {total_lines}."

            if existing_content:
                existing_lines = len(existing_content.splitlines())
                result_content += f" Previous content had {existing_lines} lines."

            return ToolResult.success_result(
                    result_content,
                    diff = FileDiff(
                        path = path ,
                        old_content= existing_content,
                        new_content= params.content ,
                        is_new_file=is_new_file
                    ),
                    metadata = {
                        "path": str(path),
                        "action": action,
                        "total_lines_written": total_lines,
                        "previous_lines": len(existing_content.splitlines()) if existing_content else 0,
                        "bytes": len(params.content.encode('utf-8'))
                        
                    }
            )

        except OSError as e:
            return ToolResult.error_result(f"Failed to write to file: {e}")


