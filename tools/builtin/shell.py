import fnmatch
import os
import shlex
from pathlib import Path
from pydantic import BaseModel, Field
from lib.constants import BLOCKED_COMMANDS
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
import subprocess

class ShellParams(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    timeout: int = Field( 120, ge=1 , le=600,  description="Timeout for the command execution in seconds")
    cwd : str | None = Field(None, description="The working directory to execute the command in (default: current directory)")


def _match_blocked(command: str) -> str | None:
    """Return the blocked pattern that matches the command, or None if safe.

    Uses token-level matching so variations like extra spaces, flags reordered,
    or quoted forms (rm -r -f /) are also caught.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    normalised = " ".join(tokens).lower()

    for blocked in BLOCKED_COMMANDS:
        # Exact substring match on the normalised token stream catches
        # whitespace variations (e.g. "rm  -rf  /" → "rm -rf /").
        if blocked.lower() in normalised:
            return blocked

    return None


class ShellTool(Tool):
    name = "shell"
    kind = ToolKind.SHELL
    description = (
        "Execute a shell command and return the output. "
        "Use this tool to run commands in the terminal and get their output. "
        "Be cautious when using this tool, as it can execute any command on the system."
        )
    schema = ShellParams


    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        params = ShellParams(**invocation.params)
        command = params.command

        matched = _match_blocked(command)
        if matched:
            return ToolConfirmation(
                tool_name=self.name,
                params=invocation.params,
                description=f"Blocked command detected: '{matched}' is not allowed for security reasons. Do you want to proceed with executing the command?",
                command=command,
                is_dangerous=True
            )
        return None


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ShellParams(**invocation.params)
        command = params.command

        # we need to ensure the command is safe to execute
        matched = _match_blocked(command)
        if matched:
            return ToolResult.error_result(f"Blocked command detected: '{matched}' is not allowed for security reasons.")

             
        cwd = invocation.cwd
        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd / cwd

        if not cwd.exists() or not cwd.is_dir():
            return ToolResult.error_result(f"Invalid working directory: {cwd}")

        env = self._build_environment()

        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=params.timeout, cwd=cwd, env=env)

            output = ""

            if result.stdout.strip():
                output += f"STDOUT:\n{result.stdout.strip()}\n"

            if result.stderr.strip():
                output += f"STDERR:\n{result.stderr.strip()}\n"

            if not output:
                output = "Command completed successfully."

            if len(output) > 100 * 1024:  # 100 KB limit
                output = output[:100 * 1024] + "\n[Output truncated due to length]"

            return ToolResult(
                success=result.returncode == 0,
                output=output.strip(),
                error=None if result.returncode == 0 else f"Command exited with return code {result.returncode}."
            )
        except subprocess.TimeoutExpired:
            return ToolResult.error_result(f"Command timed out after {params.timeout} seconds.")
        except Exception as e:
            return ToolResult.error_result(f"Error executing command: {str(e)}")


    def _build_environment(self) -> dict[str, str]:
        env = dict(os.environ)
        exclude_patterns: list[str] = ["*KEY*", "*TOKEN*", "*SECRET*", "*PASSWORD*", "*PWD*", "*AWS*", "*GCP*", "*AZURE*"]

        for key in list(env.keys()):
            if any(fnmatch.fnmatch(key.upper(), p.upper()) for p in exclude_patterns):
                del env[key]
        return env

    



if __name__ == "__main__":
    import asyncio

    tool = ShellTool()
    cwd = Path.cwd()
    invocation = ToolInvocation(cwd,params={"command": "fdisk"})
    result = asyncio.run(tool.execute(invocation))
    print(result)



