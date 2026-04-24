import re
from  pathlib  import Path

from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable
from config.config import ApprovalPolicy

from lib.contants.config import SAFE_PATTERNS


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CONFIRMATION = "needs_confirmation"

@dataclass
class ApprovalRequest:
    tool_name: str
    params: dict[str, Any]
    is_mutating: bool = False
    affected_path : list[Path] | None = None
    command: str | None = None
    is_dangerous: bool = False

def is_safe_command(command:str)->bool:
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False

class ApprovalManager:
    pass
