from pathlib import Path
from pydantic import BaseModel, Field
from lib.paths import ensure_parent_directory, resolve_path
from tools.base import FileDiff, Tool, ToolInvocation, ToolKind, ToolResult


class EditParams(BaseModel):
    path: str = Field(
            ..., 
            description="Path to the file to edit (relative to working directory or absolute path)",
    )
    old_string: str = Field(..., description="The exact text to be replaced in the file, including whitespace, indentation and punctuation. For new file , leave this as an empty string.")
    new_string: str = Field(..., description="The text to replace the old_string with.")
    replace_all: bool = Field(False, description="Whether to replace all occurrences of old_string in the file. If false, only the first occurrence will be replaced. (default: false)")

class EditTool(Tool):
    name = "edit_file"
    description = (
            "Edit a file by replacing text . this old_string must match exactly the text in the file, including whitespace and punctuation. "
            "unless repleace_all is true , use this for precise and targed edits."
            "For creating new files or complte rewrites, use write_file instead."
    )

    kind = ToolKind.WRITE

    schema = EditParams


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = EditParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)

        if not path.exists() :
            if params.old_string != "":
                return ToolResult.error_result(
                        f"File not found: {path}. To create a new file, set old_string to an empty string."
                )

        # create parent directory if it doesn't exist and write new file if it doesn't exist
        ensure_parent_directory(path)
        if not path.exists():
            path.write_text(params.new_string, encoding="utf-8")
            
            total_lines = len(params.new_string.splitlines())
            return ToolResult.success_result(
                    f"File created: {path} with {total_lines} lines.",
                    diff = FileDiff(
                        path=path,
                        old_content="",
                        new_content=params.new_string,
                        is_new_file=True
                    ),
                    metadata={"path": str(path), "lines": total_lines , "is_new_file": True}
            )


        old_content = path.read_text(encoding="utf-8")
        if not params.old_string:
            return ToolResult.error_result(
                    "old_string cannot be empty when editing an existing file. To create a new file, set old_string to an empty string and ensure the file does not already exist."
            )

        # cound the occurences of old_string in the file
        occurrences = old_content.count(params.old_string)
        print(f"Occurrences of old_string in file: {occurrences}, old_string: '{params.old_string}', file content preview: '{old_content[:100]}'")
        if occurrences == 0:
            return self._no_match_error(params.old_string, old_content, path)

        if not params.replace_all and occurrences > 1:
            return ToolResult.error_result(
                    f"old_string occurs {occurrences} times in the file."
                    "Either:\n"
                    "1. Set replace_all to true to replace all occurrences.\n"
                    "2. Modify old_string to be more specific so it only matches one occurrence.",
                    metadata={"path": str(path), "occurrences": occurrences}
            )

        new_content = old_content.replace(params.old_string, params.new_string, -1 if params.replace_all else 1)
        replace_count = occurrences if params.replace_all else 1

        if new_content == old_content:
            return ToolResult.error_result(
                    "No change made - old_string equals new_string, or replacement did not alter the content. Please verify that old_string matches the content in the file and that new_string is different.",
                    metadata={"path": str(path), "occurrences": occurrences}
            )

        try:
            path.write_text(new_content, encoding="utf-8")
            new_total_lines = len(new_content.splitlines())
            old_lines = len(old_content.splitlines())
            changed_lines = new_total_lines - old_lines
            diff_msg = ""

            
            if changed_lines > 0:
                diff_msg += f"+{changed_lines} lines added. "
            elif changed_lines < 0:
                diff_msg += f"{changed_lines} lines removed. "

            return ToolResult.success_result(
                    f"Edited file: {path}. Replaced {replace_count} occurrence(s) of old_string. {diff_msg}",
                    diff = FileDiff(
                        path=path,
                        old_content=old_content,
                        new_content=new_content,
                        is_new_file=False
                    ),
                    metadata={"path": str(path), "lines": new_total_lines , "is_new_file": False, "replacements": replace_count}
            )
        except IOError as e:
            return ToolResult.error_result(f"Error writing to file: {e}", metadata={"path": str(path)})

    def _no_match_error(self, old_string: str, content: str, path: Path) -> ToolResult:
        lines = content.splitlines()

        partial_matches = []
        search_terms = old_string.split()[:5]

        if search_terms:
            first_term = search_terms[0]
            for i, line in enumerate(lines, 1):
                if first_term in line:
                    partial_matches.append((i, line.strip()[:80]))
                    if len(partial_matches) >= 3:
                        break

        error_msg = f"old_string not found in {path}."

        if partial_matches:
            error_msg += "\n\nPossible similar lines:"
            for line_num, line_preview in partial_matches:
                error_msg += f"\n  Line {line_num}: {line_preview}"
            error_msg += "\n\nMake sure old_string matches exactly (including whitespace and indentation)."
        else:
            error_msg += (
                " Make sure the text matches exactly, including:\n"
                "- All whitespace and indentation\n"
                "- Line breaks\n"
                "- Any invisible characters\n"
                "Try re-reading the file using read_file tool and then editing."
            )

        return ToolResult.error_result(error_msg)



if __name__ == "__main__":
    tool = EditTool()
    invocation = ToolInvocation(cwd="./", params={"path": "test.md", "old_string": "Hello", "new_string": "Hi", "replace_all": True})
    result = tool.execute(invocation)
    print(result.to_model_output())



