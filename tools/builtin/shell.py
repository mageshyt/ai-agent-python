import fnmatch
import os
import shlex
import sys
import signal
import asyncio

from pathlib import Path
from pydantic import BaseModel, Field
from config.config import Config
from lib.constants import BLOCKED_COMMANDS
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult

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

        if sys.platform == "win32":
            # On Windows, use 'cmd' to execute the command
            shell_cmd = ["cmd", "/c", command]
        else:
            # On Unix-like systems, use 'sh' to execute the command
            shell_cmd = ["sh", "-c", command]

        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(cwd),
            start_new_session=True
        )
        try:

            stdout_data,stderr_data = await asyncio.wait_for(process.communicate(), timeout=params.timeout)

            # Decode the output and error streams
            stdout = stdout_data.decode('utf-8',errors='').rstrip() if stdout_data else ""
            stderr = stderr_data.decode('utf-8',errors='').rstrip() if stderr_data else ""
            exit_code = process.returncode

            output = ""

            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}\n"

            if exit_code != 0:
                output += f"Command exited with code {exit_code}"


            # compress output if it exceeds the max token limit
            if len(output) > 100*1024:
                output = output[:100*1024] + "\n\n[Output truncated due to length]"

            return ToolResult(
                    success=exit_code == 0,
                    output=output,
                    error = None if exit_code == 0 else stderr,
                    exit_code = exit_code,
                    metadata={
                        "command": command,
                        "cwd": str(cwd),
                        "timeout": params.timeout,
                    }
            )

        except asyncio.TimeoutError:
            # kill the process
            if sys.platform == "win32":
                process.kill()
                await process.wait()
            else:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                
                try:
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                        await process.wait()
                    except ProcessLookupError:
                        pass

            return ToolResult.error_result(f"Command timed out after {params.timeout} seconds.")
        except Exception as e:
            return ToolResult.error_result(f"Error executing command: {str(e)}")


    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        shell_environment =self.config.shell_environment

        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.exclude_patterns:
                keys_to_remove = [k for k in env if fnmatch.fnmatch(k.upper(), pattern.upper())]
                for key in keys_to_remove:
                    del env[key]

        if shell_environment.set_vars:
            env.update(shell_environment.set_vars)

        return env

if __name__ == "__main__":
    import asyncio
    config = Config()
    tool = ShellTool(config)
    cwd = Path.cwd()
    invocation = ToolInvocation(cwd,params={"command": "ls"})
    result = asyncio.run(tool.execute(invocation))
    print(result)



