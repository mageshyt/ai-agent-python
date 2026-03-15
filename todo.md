# AI Agent Development

## Tasks
- [x] Implement Docker tool
- [ ] Add comprehensive error handling
- [ ] Create unit tests for all tools
- [ ] Add documentation for each tool

## Tool Development Backlog

### Development Tools
- [ ] Git tool - Git operations (commit, push, status, etc.)
- [ ] Code analysis tool - Code quality analysis (linting, type checking)
- [ ] Build tool - Build system integration
- [ ] Test runner tool - Automated testing

### Productivity Tools
- [ ] Web search tool - Web search and information retrieval
- [ ] Documentation tool - Generate and manage documentation
- [ ] Dependency manager tool - Package management

### Advanced Tools
- [ ] Docker tool - Docker container management (COMPLETED)
- [ ] API tool - HTTP client for API interactions
- [ ] Database tool - Database operations

### Utility Tools
- [ ] Archive tool - Archive creation and extraction
- [ ] Checksum tool - File integrity verification
- [ ] Diff tool - File comparison

## Context Window Management (context_manager.py)

`get_context()` returns every message ever added with no truncation. On long multi-turn tasks this will silently hit the model's token limit and cause failures.

**Options to consider:**

1. **Sliding window** — keep only the last N tokens of message history. Simple to implement, but the model loses earlier context.
2. **Summarization** — when history exceeds a threshold, call the LLM to summarize older messages into a single compressed message, then resume. Preserves relevant context at the cost of an extra LLM call.
3. **Pinned messages** — always keep the first user message (the original task) + the last N turns, dropping everything in the middle.

**Relevant code:** `context/context_manager.py` → `get_context()`, `add_assistant_message()`, `add_tool_result()`

**Token counting** is already in place (`count_tokens` is called on every message), so the total budget can be calculated by summing `MessageItem.token_count`.
