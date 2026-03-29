from __future__ import annotations
import os

from typing import Any
from pydantic import BaseModel, Field, model_validator
from pathlib import Path
import dotenv

dotenv.load_dotenv()


class ModelConfig(BaseModel):
    name: str = "arcee-ai/trinity-large-preview:free" # NOTE:default model
    temperature: float = Field(default=0.7, ge=0.0, le=1.0, description="Sampling temperature for the model, between 0 and 1")
    context_window: int  = 128_000 

class MCPServerConfig(BaseModel):
    enable: bool = True
    startup_timeout: int = 30  # seconds to wait for MCP server to start before timing out
    cwd:Path | None = None

    command : str | None = None
    args : list[str] = Field(default_factory=list)
    env : dict[str, str] = Field(default_factory=dict)
    # http/sse transport settings
    url:str | None = None  # URL to connect to MCP server, if not using command/args to start it

    @model_validator(mode="after")
    def validate_transport(self) -> "MCPServerConfig":
        if self.enable:
            if self.command and self.url:
                raise ValueError("MCPServerConfig cannot have both 'command'(studio) and 'url'(http/sse) set when 'enable' is True")
            if not self.command and not self.url:
                raise ValueError("MCPServerConfig must have either 'command'(studio) or 'url'(http/sse) set when 'enable' is True")
        return self

class ShellEnvironmentPolicy(BaseModel):
    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*", "*PASSWORD*", "*PWD*", "*AWS*", "*GCP*", "*AZURE*"]
    )
    set_vars: dict[str, str] = Field(default_factory=dict)

class Config(BaseModel):
    model:ModelConfig = Field(default_factory=ModelConfig)
    cwd : Path = Field(default_factory=Path.cwd)
    max_turns : int = 100
    max_consecutive_tool_failures: int = 5
    max_tool_output_tokens : int = 50_000
    shell_environment : ShellEnvironmentPolicy = Field(default_factory=ShellEnvironmentPolicy)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict) 

    user_instructions:str | None = None
    debug: bool = False

    allowed_tools: list[str] | None = None


    @property
    def get_api_key(self) -> str | None:
        return os.getenv("API_KEY")

    @property
    def get_base_url(self) -> str | None:
        return os.getenv("BASE_URL")

    @property
    def get_model_name(self) -> str:
        return self.model.name

    @property
    def get_temperature(self) -> float:
        return self.model.temperature

    @get_model_name.setter
    def set_model_name(self, name:str) -> None:
        self.model.name = name

    @get_temperature.setter
    def set_temperature(self, temperature:float) -> None:
        if 0.0 <= temperature <= 1.0:
            self.model.temperature = temperature
        else:
            raise ValueError("Temperature must be between 0 and 1")


    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.get_api_key:
            errors.append("API_KEY environment variable is not set")

        if not self.get_base_url:
            errors.append("BASE_URL environment variable is not set")

        if not self.cwd.exists() or not self.cwd.is_dir():
            errors.append(f"CWD path '{self.cwd}' does not exist or is not a directory")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
