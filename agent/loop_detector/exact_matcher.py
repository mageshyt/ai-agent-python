import time
from dataclasses import dataclass, field
from typing import Any

from agent.loop_detector.base import ActionRecord, Detector, LoopDetectionResult, LoopType
from lib import _hash_args


@dataclass
class ExactMatchDetector(Detector):
    threshold: int = 2

    _seen: dict[str, list[ActionRecord]] = field(default_factory=dict,init=False,repr=False)

    def record(self, tool: str, args: dict[str, Any], output: str, turn_index: int) -> LoopDetectionResult:
        args_hash = _hash_args(args)

        key = f"{tool}:{args_hash}"

        if key not in self._seen:
            self._seen[key] = []
        action = ActionRecord(
            id=f"{tool}_{turn_index}",
            tool=tool,
            args=args,
            argsHash=args_hash,
            output=output,
            outputHash=str(hash(output)),
            timestamp=int(time.time()),
            turnIndex=turn_index
        )
        self._seen[key].append(action)

        if len(self._seen[key]) >= self.threshold:
            return LoopDetectionResult(
                is_loop=True,
                detector=LoopType.EXACT,
                confidence=1.0,
                repeat_count=len(self._seen[key]),
                evidence=f"Action {tool} with args {args} has been repeated {len(self._seen[key])} times.",
                suggestion="Consider changing the arguments or tool to break the loop."
            )

        return LoopDetectionResult(is_loop=False)

    def reset(self) -> None:
        self._seen.clear()
 
    def history(self) -> dict[str, list[ActionRecord]]:
        return dict(self._seen)
 
    def stats(self) -> dict[str, int]:
        return {key: len(records) for key, records in self._seen.items()}


if __name__ == "__main__":
    print("=== ExactMatchDetector smoke test ===\n")
 
    det = ExactMatchDetector(threshold=2)
 
    calls = [
        ("read_file", {"path": "/etc/hosts"},   "127.0.0.1 localhost"),
        ("bash",      {"cmd": "ls -la"},         "total 42\n..."),
        ("read_file", {"path": "/etc/hosts"},   "127.0.0.1 localhost"),  # repeat!
        ("read_file", {"path": "/etc/passwd"},  "root:x:0:0:..."),       # different args → ok
        ("bash",      {"cmd": "ls -la"},         "total 42\n..."),        # repeat!
    ]
 
    for i, (tool, args, output) in enumerate(calls):
        result = det.record(tool, args, output, turn_index=i)
        status = "🔴 LOOP" if result.is_loop else "✅ ok  "
        print(f"Turn {i}  {status}  {tool}({args})")
        if result.is_loop:
            print(f"          {result.evidence}")
            print(f"          {result.suggestion}")
        print()
 
    print("Stats:", det.stats())
