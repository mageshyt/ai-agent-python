import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional
import fnmatch

from pydantic import BaseModel, Field
from config.config import Config
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult


class DockerParams(BaseModel):
    command: str = Field(
        ...,
        description="Docker command to execute (e.g., 'build', 'run', 'ps', 'images', 'logs', 'exec')"
    )
    arguments: List[str] = Field(
        default_factory=list,
        description="List of arguments for the Docker command"
    )
    timeout: int = Field(
        120,
        ge=1,
        le=600,
        description="Timeout for the command execution in seconds"
    )
    cwd: str | None = Field(
        None,
        description="Working directory to execute the command in (default: current directory)"
    )
    container: str | None = Field(
        None,
        description="Container name or ID (required for commands like 'exec', 'logs', 'stop')"
    )
    file: str | None = Field(
        None,
        description="Dockerfile path (required for 'build' command)"
    )
    tag: str | None = Field(
        None,
        description="Image tag (required for 'build' command)"
    )


class DockerTool(Tool):
    name = "docker"
    kind = ToolKind.SHELL
    description = (
        "Execute Docker commands to manage containers and images. "
        "Supports commands like 'build', 'run', 'ps', 'images', 'logs', 'exec', 'stop', 'start', 'rm', and 'rmi'. "
        "Be cautious when using commands that can modify or remove containers and images."
        "For 'build' command, you must provide a Dockerfile path and an image tag. "
        "For 'exec', 'logs', and 'stop' commands, you must provide a container name or ID."

        )
    schema = DockerParams


    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        params = DockerParams(**invocation.params)
        
        # Check for potentially dangerous operations
        dangerous_commands = ["rm", "rmi", "stop", "kill"]
        if params.command in dangerous_commands:
            return ToolConfirmation(
                tool_name=self.name,
                params=invocation.params,
                description=f"Potentially destructive Docker command detected: '{params.command}'. Do you want to proceed?",
                command=f"docker {params.command}",
                is_dangerous=True
            )
        
        # Check for build operations which might use system resources
        if params.command == "build":
            return ToolConfirmation(
                tool_name=self.name,
                params=invocation.params,
                description=f"Docker build operation detected. This may use significant system resources. Do you want to proceed?",
                command=f"docker {params.command}",
                is_dangerous=False
            )
        
        return None


    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = DockerParams(**invocation.params)
        
        # Validate required parameters for specific commands
        if params.command == "build":
            if not params.file:
                return ToolResult.error_result("Dockerfile path is required for 'build' command")
            if not params.tag:
                return ToolResult.error_result("Image tag is required for 'build' command")
        elif params.command in ["exec", "logs", "stop"]:
            if not params.container:
                return ToolResult.error_result(f"Container name/ID is required for '{params.command}' command")
        
        # Build the Docker command
        docker_cmd = ["docker", params.command] + params.arguments
        
        if params.command == "build":
            docker_cmd.extend(["-f", params.file, "-t", params.tag, "."])
        elif params.command == "exec":
            docker_cmd.extend([params.container] + params.arguments)
        elif params.command == "logs":
            docker_cmd.extend([params.container] + params.arguments)
        elif params.command == "stop":
            docker_cmd.extend([params.container] + params.arguments)
        elif params.command == "run":
            if not params.arguments:
                return ToolResult.error_result("At least one argument is required for 'run' command")
            docker_cmd.extend(params.arguments)
        
        # Convert command to string for display and logging
        command_str = " ".join(docker_cmd)
        
        cwd = invocation.cwd
        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd / cwd
        
        if not cwd.exists() or not cwd.is_dir():
            return ToolResult.error_result(f"Invalid working directory: {cwd}")
        
        env = self._build_environment()
        
        if sys.platform == "win32":
            shell_cmd = ["cmd", "/c"] + docker_cmd
        else:
            shell_executable = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
            shell_cmd = [shell_executable, "-c", " ".join(docker_cmd)]
        
        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(cwd),
            start_new_session=True
        )
        
        try:
            stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=params.timeout)
            
            stdout = stdout_data.decode('utf-8', errors='').rstrip() if stdout_data else ""
            stderr = stderr_data.decode('utf-8', errors='').rstrip() if stderr_data else ""
            exit_code = process.returncode
            
            output = ""
            
            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}\n"
            
            if exit_code != 0:
                output += f"Command exited with code {exit_code}"
            
            # Compress output if it exceeds the max token limit
            if len(output) > 100*1024:
                output = output[:100*1024] + "\n\n[Output truncated due to length]"
            
            return ToolResult(
                success=exit_code == 0,
                output=output,
                error=None if exit_code == 0 else stderr,
                exit_code=exit_code,
                metadata={
                    "command": command_str,
                    "cwd": str(cwd),
                    "timeout": params.timeout,
                    "docker_command": params.command,
                    "arguments": params.arguments,
                }
            )
            
        except asyncio.TimeoutError:
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
            
            return ToolResult.error_result(f"Docker command timed out after {params.timeout} seconds.")
        except Exception as e:
            return ToolResult.error_result(f"Error executing Docker command: {str(e)}")


    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        shell_environment = self.config.shell_environment
        
        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.exclude_patterns:
                keys_to_remove = [k for k in env if fnmatch.fnmatch(k.upper(), pattern.upper())]
                for key in keys_to_remove:
                    del env[key]
        
        if shell_environment.set_vars:
            env.update(shell_environment.set_vars)
        
        return env


# Common Docker operations for reference
DOCKER_OPERATIONS = {
    "build": {
        "description": "Build an image from a Dockerfile",
        "required": ["file", "tag"],
        "example": "docker build -f Dockerfile -t myimage:1.0 ."
    },
    "run": {
        "description": "Create and run a container from an image",
        "required": ["image"],
        "example": "docker run -d -p 80:80 nginx"
    },
    "ps": {
        "description": "List containers",
        "example": "docker ps -a"
    },
    "images": {
        "description": "List images",
        "example": "docker images"
    },
    "logs": {
        "description": "Fetch logs of a container",
        "required": ["container"],
        "example": "docker logs my_container"
    },
    "exec": {
        "description": "Run a command in a running container",
        "required": ["container"],
        "example": "docker exec -it my_container bash"
    },
    "stop": {
        "description": "Stop a running container",
        "required": ["container"],
        "example": "docker stop my_container"
    },
    "start": {
        "description": "Start a stopped container",
        "required": ["container"],
        "example": "docker start my_container"
    },
    "rm": {
        "description": "Remove a container",
        "required": ["container"],
        "example": "docker rm my_container"
    },
    "rmi": {
        "description": "Remove an image",
        "required": ["image"],
        "example": "docker rmi my_image:1.0"
    }
}


if __name__ == "__main__":
    import asyncio
    config = Config()
    tool = DockerTool(config)
    cwd = Path.cwd()
    invocation = ToolInvocation(cwd, params={"command": "ps", "arguments": ["-a"]})
    result = asyncio.run(tool.execute(invocation))
    print(result)
