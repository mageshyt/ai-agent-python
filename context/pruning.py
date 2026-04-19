from dataclasses import dataclass
from context.context_manager import ContextManager, MessageItem
from lib.text import count_tokens


@dataclass
class PruningConfig:
    """Configuration for sliding window pruning."""
    max_window_tokens: int = 32000
    keep_recent_messages: int = 6
    keep_recent_tool_results: int = 8
    preserve_system: bool = True
    preserve_sticky: bool = True
    sticky_keywords: list[str] | None = None

    def __post_init__(self):
        if self.max_window_tokens <= 0:
            raise ValueError("max_window_tokens must be > 0")
        if self.keep_recent_messages <= 0:
            raise ValueError("keep_recent_messages must be > 0")
        if self.keep_recent_tool_results < 0:
            raise ValueError("keep_recent_tool_results must be >= 0")

        if self.sticky_keywords is None:
            self.sticky_keywords = [
                "decision", "refactored", "bug", "fix", "api",
                "config", "important", "critical", "created",
                "deleted", "moved", "renamed"
            ]


class SlidingWindowPruner:
    """Sliding window based context pruning."""

    def __init__(self, config: PruningConfig | None = None):
        self.config = config or PruningConfig()
        self._cached_signature: tuple[int, int] | None = None
        self._cached_total_tokens: int = 0

    def _context_signature(self, messages: list[MessageItem]) -> tuple[int, int]:
        if not messages:
            return (0, 0)
        return (len(messages), id(messages[-1]))

    def _compute_total_tokens(self, messages: list[MessageItem]) -> int:
        signature = self._context_signature(messages)
        if self._cached_signature == signature:
            return self._cached_total_tokens

        total = sum(m.token_count or self._count_message_tokens(m) for m in messages)
        self._cached_signature = signature
        self._cached_total_tokens = total
        return total

    def prune(self, context_manager: ContextManager) -> int:
        messages = context_manager._messages
        if not messages or len(messages) <= self.config.keep_recent_messages:
            return 0 # No pruning needed

        preserved: list[MessageItem] = []
        preserved_ids: set[int] = set()

        system_msgs = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]

        idx_map = { id(m): i for i, m in enumerate(messages) }
        
        if self.config.preserve_system:
            for msg in system_msgs:
                preserved.append(msg)
                preserved_ids.add(id(msg))

        total_tokens = sum(self._count_message_tokens(m) for m in preserved)
        recent_message_cutoff = len(messages) - self.config.keep_recent_messages # keep (n) recent messages 

        for msg in non_system:
            msg_position = idx_map[id(msg)]
            if msg_position >= recent_message_cutoff:
                preserved.append(msg)
                preserved_ids.add(id(msg))
                total_tokens += (msg.token_count or self._count_message_tokens(msg))

        # explicitly preserve sticky older messages before normal prioritization.
        sticky_older = [m for m in non_system if id(m) not in preserved_ids and self._is_sticky(m)]
        sticky_older_sorted = sorted(sticky_older, key=lambda m: -idx_map[id(m)])

        for msg in sticky_older_sorted:
            msg_token = msg.token_count or self._count_message_tokens(msg)
            if total_tokens + msg_token <= self.config.max_window_tokens:
                preserved.append(msg)
                preserved_ids.add(id(msg))
                total_tokens += msg_token

        # fill remaining budget with higher-priority older messages.
        older_candidates = [m for m in non_system if id(m) not in preserved_ids]
        older_candidates_sorted = sorted(
            older_candidates,
            key=lambda m: (self._get_message_priority(m), -idx_map[id(m)]),
        )

        kept_older_tool_results = 0

        for msg in older_candidates_sorted:
            if total_tokens >= self.config.max_window_tokens:
                break

            msg_token = msg.token_count or self._count_message_tokens(msg)

            # keep older tool results up to limit
            if msg.role == "tool":
                if kept_older_tool_results < self.config.keep_recent_tool_results and total_tokens + msg_token <= self.config.max_window_tokens:
                    preserved.append(msg)
                    preserved_ids.add(id(msg))
                    total_tokens += msg_token
                    if not self._is_sticky(msg):
                        kept_older_tool_results += 1
                    continue


            if total_tokens + msg_token <= self.config.max_window_tokens:
                preserved.append(msg)
                preserved_ids.add(id(msg))
                total_tokens += msg_token

        
        # rebuild original order
        preserved.sort(key=lambda m: idx_map[id(m)])
        removed_count = len(messages) - len(preserved)
        
        context_manager._messages = preserved
        self._cached_signature = self._context_signature(preserved)
        self._cached_total_tokens = total_tokens
        return removed_count



    def _is_sticky(self, message:MessageItem) -> bool:
        """Determine if a message is sticky based on its content and the configuration."""
        if not message.content or not self.config.preserve_sticky:
            return False
        if not self.config.sticky_keywords:
            return False
        content_lower = message.content.lower()
        return any(keyword in content_lower for keyword in self.config.sticky_keywords)

    def _count_message_tokens(self, message: MessageItem) -> int:
        """Count the number of tokens in a message."""
        if not message.content:
            return 0
        return count_tokens(message.content)

    def _get_message_priority(self, message: MessageItem) -> int:
        """Lower number = higher priority (keep longer)."""
        if message.role == "system":
            return 0
        if message.role == "tool":
            return 1
        if message.role == "assistant":
            return 2
        return 3  # user messages

    def should_prune(self, context_manager: ContextManager) -> bool:
        """Check if pruning is needed based on token count."""
        total = self._compute_total_tokens(context_manager._messages)
        return total >= self.config.max_window_tokens
