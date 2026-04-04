# TODO

## Context Window Management (context_manager.py)

`get_context()` returns every message ever added with no truncation. On long multi-turn tasks this will silently hit the model's token limit and cause failures.

**Options to consider:**

1. **Sliding window** — keep only the last N tokens of message history. Simple to implement, but the model loses earlier context.
2. **Summarization** — when history exceeds a threshold, call the LLM to summarize older messages into a single compressed message, then resume. Preserves relevant context at the cost of an extra LLM call.
3. **Pinned messages** — always keep the first user message (the original task) + the last N turns, dropping everything in the middle.

**Relevant code:** `context/context_manager.py` → `get_context()`, `add_assistant_message()`, `add_tool_result()`

**Token counting** is already in place (`count_tokens` is called on every message), so the total budget can be calculated by summing `MessageItem.token_count`.

---

## MCP Feature Enhancements

### Connection Timeout Handling
- Add retry logic with exponential backoff for failed MCP connections
- Implement configurable retry attempts and delays
- Ensure graceful degradation when servers are unavailable

**Files to modify:** `tools/mcp/mcp_manager.py`, `tools/mcp/client.py`

### Connection Status Monitoring
- Add periodic health checks for connected MCP servers
- Implement automatic reconnection for failed connections
- Add connection status reporting to the UI

**Files to modify:** `tools/mcp/mcp_manager.py`

### Tool Caching and Refresh
- Add capability to refresh tool list from MCP servers dynamically
- Implement tool discovery polling for servers that support it
- Add cache invalidation strategy for updated tools

**Files to modify:** `tools/mcp/mcp_manager.py`, `tools/mcp/client.py`

### Enhanced Error Reporting
- Add more context to error messages (server name, connection type)
- Implement structured logging for MCP operations
- Add error recovery suggestions

**Files to modify:** `tools/mcp/client.py`, `tools/mcp/mcp_manager.py`

### Configuration Validation Enhancement
- Add comprehensive validation for MCP server configurations
- Validate command arguments and URL formats
- Add environment variable validation

**Files to modify:** `config/config.py`

### Graceful Shutdown Improvements
- Add coordination for ongoing tool calls during shutdown
- Implement timeout for tool execution during shutdown
- Add cleanup hooks for MCP resources

**Files to modify:** `tools/mcp/mcp_manager.py`, `agent/agent.py`

### Logging Enhancement
- Add structured logging for MCP operations
- Implement debug logging for connection details
- Add performance metrics logging

**Files to modify:** `tools/mcp/client.py`, `tools/mcp/mcp_manager.py`

### Configuration Hot-reload
- Add dynamic MCP configuration updates without restart
- Implement server addition/removal at runtime
- Add configuration change detection

**Files to modify:** `tools/mcp/mcp_manager.py`, `config/config.py`
