from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from pydantic.json_schema import model_json_schema


class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    MEMORY = "memory"
    FILE_SYSTEM = "file_system"
    MCP = "mcp"


@dataclass
class ToolInvocation:
    cwd: Path
    params: dict[str, Any]


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False

    @classmethod
    def error_result(cls, error: str, output: str = "",**kwargs):
        return cls(success=False, error=error, output=output, **kwargs)

    @classmethod
    def success_result(cls, output: str, **kwargs):
        return cls(success=True, output=output, **kwargs)

    def to_model_output(self)->str:
        if self.success:
            return self.output
        else:
            return f"Error: {self.error}\nOutput: {self.output}"

@dataclass
class ToolConfirmation:
    tool_name: str
    params: dict[str, Any]
    description: str


class Tool(ABC):
    name: str = "base_tool"
    description: str = "this is the base tool"
    kind: ToolKind = ToolKind.READ

    def __init__(self) -> None:
        super().__init__()

    @property
    def schema(self) -> dict[str, Any] | type["BaseModel"]:
        raise NotImplementedError("tool must define abstract property")

    @abstractmethod
    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                schema(**params)
            except ValidationError as e:
                errors = []
                for error in e.errors():
                    loc = ".".join(str(loc) for loc in error["loc"])
                    msg = error["msg"]
                    errors.append(f"{loc}: {msg}")
                return errors
            except Exception as e:
                return [str(e)]
        return []

    def is_mutating(self) -> bool:
        return self.kind in {
            ToolKind.WRITE,
            ToolKind.SHELL,
            ToolKind.NETWORK,
            ToolKind.MCP,
        }

    def is_external(self) -> bool:
        return self.kind in {ToolKind.SHELL, ToolKind.NETWORK, ToolKind.MCP}

    async def get_confirmation(
        self, invocation: ToolInvocation
    ) -> ToolConfirmation | None:
        if not self.is_mutating():
            return None

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Are you sure you want to execute the {self.name} tool with the following parameters?\n{invocation.params}",
        )

    def to_openai_schema(self) -> dict[str, Any]:
        schema = self.schema
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            json_schema = model_json_schema(schema, mode="serialization")

            return {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": json_schema.get("properties", {}),
                    "required": json_schema.get("required", []),
                },
            }

        if isinstance(schema, dict):
            return {
                "name": self.name,
                "description": self.description,
                "parameters": schema
                if "parameters" not in schema
                else schema["parameters"],
            }

        raise ValueError(
            f"Invalid schema type for tool {self.name}. Must be either a Pydantic model or a dict representing the JSON schema."
        )
