import os
import sys
import json
import signal
import asyncio
import tempfile
import shlex
from typing import Any, TYPE_CHECKING

from config.config import Config, HookConfig, HookTrigger

import logging

if TYPE_CHECKING:
    from tools.base import ToolResult

logger = logging.getLogger(__name__)

class HookSystem:
    def __init__(self,config:Config) -> None:
        self.config = config
        self.hooks: list[HookConfig] = []

        if self.config.hooks_enabled:
            logger.info(f"Hook system initialized with {len(self.hooks)} hooks")
            self.hooks = [hook for hook in self.config.hooks if hook.enable] # pick only enabled hooks

    async def execute_before_agent(self, user_message:str) -> None:
        env = self._build_environment(HookTrigger.BEFORE_AGENT_TURN , user_message)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT_TURN:
                await self._execute_hook(hook,env)

    
    async def execute_after_agent(self, user_message:str,agent_response:str) -> None:
        env = self._build_environment(HookTrigger.AFTER_AGENT_TURN , user_message)
        env["AI_AGENT_RESPONSE"] = agent_response
        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_AGENT_TURN:
                await self._execute_hook(hook,env)

    async def execute_before_tool(self, tool_name:str, tool_params:dict[str,Any]) -> None:
        env = self._build_environment(HookTrigger.BEFORE_TOOL_CALL ,tool_name=tool_name)

        env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_TOOL_CALL:
                await self._execute_hook(hook,env)

    async def execute_after_tool(self, tool_name:str,tool_params:dict[str,Any],tool_result : 'ToolResult') -> None:
        env = self._build_environment(HookTrigger.AFTER_TOOL_CALL, tool_name=tool_name)
        env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
        env["AI_AGENT_TOOL_RESULT"] = tool_result.to_model_output()
        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_TOOL_CALL:
                await self._execute_hook(hook,env)
    async def execute_on_error(self, error:Exception ) -> None:
        env = self._build_environment(HookTrigger.ON_ERROR, error=error)
        for hook in self.hooks:
            if hook.trigger == HookTrigger.ON_ERROR:
                await self._execute_hook(hook,env)

    async def _execute_hook(self, hook: HookConfig,env:dict[str,str]) -> None:
        logger.info(f"Executing hook '{hook.name}' with command '{hook.command}' and script '{hook.script}'")
        try:
            if hook.command:
                await self._run_command(hook.command, timeout=hook.timeout,env=env,name=hook.name)
            else:
                with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.sh') as tmp_script:
                    tmp_script.write("#!/bin/bash\n")
                    tmp_script.write(hook.script or "")
                    tmp_script_path = tmp_script.name


                try:
                    # NOTE: we have to set execute permissions on the temp script file for it to run
                    os.chmod(tmp_script_path, 0o755)
                    await self._run_command(tmp_script_path, timeout=hook.timeout,env=env,name=hook.name)
                finally:
                    # we can remove the temp script file immediately after starting the process since it will be loaded into memory
                        os.unlink(tmp_script_path)

        except Exception as e:
            logger.error(f"Error executing hook '{hook.name}': {e}")

    async def _run_command(self, command:str , timeout:float,env:dict[str,str],name) -> None:
        cmd = shlex.split(command)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.config.cwd,
            start_new_session=True
        )
        try:

           await asyncio.wait_for(process.communicate(), timeout=timeout)

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
        except Exception as e:
            logger.error(f"Error executing hook '{name}': {e}")

    def _build_environment(
        self,
        trigger: HookTrigger,
        user_message: str | None = None,
        error : Exception | None = None,
        tool_name : str | None = None
    ) -> dict[str, str]:
        env = os.environ.copy()

        env["AI_AGENT_TRIGGER"] = trigger.value
        env["AI_AGENT_CWD"] = str(self.config.cwd)

        if tool_name:
            env["AI_AGENT_TOOL_NAME"] = tool_name

        if user_message:
            env["AI_AGENT_USER_MESSAGE"] = user_message

        if error:
            env["AI_AGENT_ERROR"] = str(error)

        return env

