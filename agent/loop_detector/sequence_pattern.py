import time
from dataclasses import dataclass, field
from typing import Any

from agent.loop_detector.base import ActionRecord, Detector, LoopDetectionResult, LoopType
from lib import _hash_args


@dataclass
class SequencePatternDetector(Detector):
    min_pattern_len: int = 2
    max_pattern_len: int = 6
    min_repetitions: int = 2
 
    _keys: list[str] = field(default_factory=list, init=False, repr=False)
 
 
    def record(self, tool: str, args: dict[str, Any], output: str, turn_index: int) -> LoopDetectionResult:
        key = f"{tool}:{_hash_args(args)[:8]}"
        self._keys.append(key)
 
        return self._check_patterns(turn_index)
 
    def reset(self) -> None:
        self._keys.clear()
 
    def _check_patterns(self, turn_index: int) -> LoopDetectionResult:
        seq = self._keys
        total = len(seq)
 
        # need at least 2 × min_pattern_len keys before we can match
        if total < self.min_pattern_len * 2:
            return LoopDetectionResult(is_loop=False, detector=LoopType.SEQUENCE)
 
        # try each candidate pattern length
        for pat_len in range(self.min_pattern_len, min(self.max_pattern_len + 1, total // 2 + 1)):
            repetitions, pattern = self._count_repetitions(seq, pat_len)
            if repetitions >= self.min_repetitions:
                confidence = self._confidence(repetitions)
                readable = " → ".join(pattern)
                return LoopDetectionResult(
                    is_loop=True,
                    detector=LoopType.SEQUENCE,
                    confidence=confidence,
                    repeat_count=repetitions,
                    evidence=(
                        f"Pattern [{readable}] repeated {repetitions}x "
                        f"(pattern length={pat_len}, detected at turn {turn_index})"
                    ),
                    suggestion=(
                        "The agent is cycling through the same sequence of tool calls "
                        "without making progress. Consider breaking the cycle by changing "
                        "the goal, skipping a step, or using a different tool."
                    ),
                )
 
        return LoopDetectionResult(is_loop=False, detector=LoopType.SEQUENCE)
 
    @staticmethod
    def _count_repetitions(seq: list[str], pat_len: int) -> tuple[int, list[str]]:
        if len(seq) < pat_len * 2:
            return 0, []
 
        # candidate pattern = the most recent `pat_len` keys
        pattern = seq[-pat_len:]
        reps = 1
        pos = len(seq) - pat_len * 2  # start of the previous block
 
        while pos >= 0:
            block = seq[pos: pos + pat_len]
            if block == pattern:
                reps += 1
                pos -= pat_len
            else:
                break
 
        return reps, pattern
 
    @staticmethod
    def _confidence(repetitions: int) -> float:
        return min(0.95, 0.5 + repetitions * 0.15)

    def stats(self) -> dict[str, int]:
        return {"total_calls": len(self._keys)}
    
    def history(self) -> dict[str, list[ActionRecord]]:
        return {"calls": [ActionRecord(id=str(i), tool=key.split(":")[0], args={}, argsHash=key.split(":")[1], output="", outputHash="", timestamp=0, turnIndex=i) for i, key in enumerate(self._keys)]}
