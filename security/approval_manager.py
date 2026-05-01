import re
from  pathlib  import Path

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from config.config import ApprovalPolicy

from lib import is_dangerous_command, is_safe_command
from tools.base import ToolConfirmation


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
class ApprovalManager:
    def __init__(
        self,
        approval_policy: ApprovalPolicy,
        cwd : Path,
        user_confirmation_callback: Callable[[ToolConfirmation], bool] | None = None,
    ):
        self.approval_policy = approval_policy
        self.user_confirmation_callback = user_confirmation_callback
        self.cwd = cwd

    
    async def check_approval(self,request:ApprovalRequest)->ApprovalStatus:
        # no mutation (read onyl tool)
        if not request.is_mutating:
            return ApprovalStatus.APPROVED

        if request.command:
            decision = self._assess_risk(request.command)

            if decision != ApprovalStatus.NEEDS_CONFIRMATION:
                return decision
        if request.affected_path:
            for path in request.affected_path:
                if not path.is_relative_to(self.cwd):
                    return ApprovalStatus.NEEDS_CONFIRMATION
        
        if request.is_dangerous:
            if self.approval_policy == ApprovalPolicy.YOLO:
                return ApprovalStatus.APPROVED
            return ApprovalStatus.NEEDS_CONFIRMATION

        return ApprovalStatus.APPROVED



    def _assess_risk(self, command: str) -> ApprovalStatus:
        # if the policy is "Yolo", approve everything
        if self.approval_policy == ApprovalPolicy.YOLO:
            return ApprovalStatus.APPROVED

        # check if the command is dangerous

        if is_dangerous_command(command):
            return ApprovalStatus.REJECTED

        if self.approval_policy == ApprovalPolicy.NEVER:
            if is_safe_command(command):
                return ApprovalStatus.APPROVED
            return ApprovalStatus.REJECTED

        if self.approval_policy == ApprovalPolicy.AUTO_EDIT:
            if is_safe_command(command):
                return ApprovalStatus.APPROVED
            return ApprovalStatus.NEEDS_CONFIRMATION

        if self.approval_policy in {ApprovalPolicy.AUTOMATIC , ApprovalPolicy.ON_REQUEST}:
            return ApprovalStatus.APPROVED


        return ApprovalStatus.NEEDS_CONFIRMATION

    async def request_approval(self, confirmation:ToolConfirmation):
        if self.user_confirmation_callback:
            result = self.user_confirmation_callback(confirmation)
            return result
        return  True
