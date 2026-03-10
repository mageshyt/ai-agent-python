import asyncio

from pydantic import BaseModel, Field

from lib import MAX_FILE_SIZE,check_file_size, is_binary_file, resolve_path ,  count_tokens, truncate_text_by_tokens
from tools import Tool, ToolInvocation, ToolKind, ToolResult


class ReadFileParams(BaseModel):
    path: str = Field(
        ..., description="path to the field to read (e.g., '/path/to/file.txt')"
    )
    offset: int = Field(
        1, description="offset to start reading from (default: 1)", ge=1
    )
    limit: int | None = Field(None, description="limit to read (default: None)", ge=1)


class ReadFileTool(Tool):
    name = "read_file"
    kind = ToolKind.READ
    description = (
        "Read the contents of a text file. Returns the file contents as a string with line numbers"
        "For large files ,use offset and limit to read in chunks"
        "Cannot read binary files (e.g., images, videos)"
    )
    schema = ReadFileParams

    MAX_OUTPUT_TOKENS = 15000 # maximum tokens to return in the output

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists():
            return ToolResult.error_result(f"File not found: {path}")

        if not path.is_file():
            return ToolResult.error_result(f"Path is not a file: {path.name}")

        # check the file size , whether it exceeds the limit
        if not check_file_size(path):
            file_size_mb = path.stat().st_size / (1024 * 1024)
            return ToolResult.error_result(
                f"File is too large ({file_size_mb:.1f} MB)"
                f" Maximum allowed size is {MAX_FILE_SIZE / (1024 * 1024):.1f} MB"
            )

        if is_binary_file(path):
            return ToolResult.error_result(
                f"Cannot read binary files: {path.name}"
                "This tool is designed for text files only."
            )

        # read the file
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")

        try:
            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult.success_result(
                    "File is empty", metadata={"total_lines": total_lines}
                )

            # apply offset and limit
            start_idx = max(0, params.offset - 1)
            if params.limit is not None:
                end_idx = min(start_idx + params.limit, total_lines)
            else:
                end_idx = total_lines
            formated_lines = []

            for idx ,  line in enumerate(lines[start_idx:end_idx], start=start_idx + 1):
                formated_lines.append(f"{idx:6}| {line}")

            output = "\n".join(formated_lines)

            token_cont = count_tokens(output, model="gpt-4") # TODO: make the model configurable

            # if the output exceeds the token limit, we need to truncate it
            if token_cont > self.MAX_OUTPUT_TOKENS:
                output = truncate_text_by_tokens(
                    output,
                    max_tokens=self.MAX_OUTPUT_TOKENS,
                    model="gpt-4", # TODO: make the model configurable
                    suffix=f"\n...[output truncated {token_cont} tokens, showing first {self.MAX_OUTPUT_TOKENS} tokens]",
                    preserve_lines=False, # for file content, we can truncate by characters to better utilize the token limit
                )

                metadata_lines = []

                if start_idx > 0 or end_idx < total_lines:
                    metadata_lines.append(f"Showing lines {start_idx + 1} to {end_idx} of {total_lines}")

                if metadata_lines:
                    header = " | ".join(metadata_lines) + "\n" + "-" * 80
                    output = header + "\n" + output

            return ToolResult.success_result(
                output,
                truncated = token_cont > self.MAX_OUTPUT_TOKENS,
                metadata={"total_lines": total_lines, 
                          "start_line": start_idx + 1, 
                          "end_line": end_idx ,
                          "path": str(path)
                          }
            )
        except Exception as e:
                return ToolResult.error_result(f"Error reading file: {str(e)}")
    

if __name__ == "__main__":
    import os

    read_tool = ReadFileTool()
    print(f"Current working directory: {os.getcwd()}")
    invocation = ToolInvocation(
        cwd=os.getcwd(), params={"path": "./tools/base.py", "offset": 1,"limit": 100}
    )
    result = asyncio.run(read_tool.execute(invocation))
    print(result.output)
