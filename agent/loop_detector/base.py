from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

@dataclass
class ActionRecord:
    id: str
    tool: str
    args: dict[str, Any]
    argsHash: str
    output: str
    outputHash: str
    timestamp: int
    turnIndex: int

class LoopType(str,Enum):
    EXACT = "exact"
    SEQUENCE = "sequence"
    STAGNATION = "stagnation"

@dataclass
class LoopDetectionResult:
    is_loop: bool
    detector: LoopType | None = None
    confidence: float = 0.0
    repeat_count: int = 0
    evidence: str = ""
    suggestion: str = ""
 

class Detector(ABC):
    @abstractmethod
    def record(self, tool: str, args: dict[str, Any], output: str, turn_index: int) -> LoopDetectionResult:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def history(self) -> dict[str, list[ActionRecord]]:
        raise NotImplementedError

    @abstractmethod
    def stats(self) -> dict[str, int]:
        raise NotImplementedError
