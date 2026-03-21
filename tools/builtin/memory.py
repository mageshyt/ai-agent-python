from config.config import Config
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind
from pydantic import BaseModel, Field

 
class MemoryParams(BaseModel):
    action: str = Field(
        ..., description="Action: 'set', 'get', 'delete', 'list', 'clear'"
    )
    key: str | None = Field(
        None, description="Memory key (required for `set`, `get`, `delete`)"
    )
    value: str | None = Field(None, description="Value to store (required for `set`)")


