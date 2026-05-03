import asyncio
import os

import pytest

from config.config import Config, HookConfig, HookTrigger
from hooks.hook_system import HookSystem
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.registry import ToolRegistry


class BadParamsTool(Tool):
    name = "bad_params"
    kind = ToolKind.WRITE
    schema = {}

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.execute_called = False

    def validate_params(self, params: dict) -> list[str]:
        return ["invalid params"]

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        self.execute_called = True
        return ToolResult.success_result("ok")


class ExplodingTool(Tool):
    name = "explode"
    kind = ToolKind.WRITE
    schema = {}

    def validate_params(self, params: dict) -> list[str]:
        return []

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        raise RuntimeError("boom")


def test_hook_command_string_not_split(monkeypatch):
    config = Config()
    hook_system = HookSystem(config)
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args

        class DummyProcess:
            async def communicate(self):
                return (b"", b"")

        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    asyncio.run(hook_system._run_command("echo hi", timeout=1, env={}, name="test"))
    assert captured["args"][:2] == ("echo", "hi")


def test_hook_script_not_deleted_before_execution(monkeypatch):
    config = Config()
    hook_system = HookSystem(config)
    hook = HookConfig(
        name="script_hook",
        trigger=HookTrigger.BEFORE_AGENT_TURN,
        script="echo hi",
    )
    called = {}

    async def fake_run_command(command: str, timeout: int, env: dict, name: str) -> None:
        called["exists"] = os.path.exists(command)

    monkeypatch.setattr(hook_system, "_run_command", fake_run_command)

    asyncio.run(hook_system._execute_hook(hook, env={}))
    assert called.get("exists") is True


def test_validation_error_does_not_execute_tool():
    config = Config()
    registry = ToolRegistry(config)
    tool = BadParamsTool(config)
    registry.register_tool(tool)

    asyncio.run(registry.invoke_tool(tool.name, params={}, cwd=None))
    assert tool.execute_called is False


def test_execute_exception_returns_tool_result():
    config = Config()
    registry = ToolRegistry(config)
    tool = ExplodingTool(config)
    registry.register_tool(tool)

    result = asyncio.run(registry.invoke_tool(tool.name, params={}, cwd=None))
    assert isinstance(result, ToolResult)
    assert result.success is False
