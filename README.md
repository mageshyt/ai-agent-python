# AI CLI Agent

An extensible AI-powered command-line agent with tool execution, subagents, session persistence, and model auto-selection.

This project is built for learning, experimentation, and personal productivity — inspired by tools like Claude Code and Gemini CLI.

---

## ✨ Features

### Core Agent
- Multi-turn conversations
- Tool calling with schema validation
- Streaming responses
- Loop detection
- Context compression

### Tools
- File operations (read, write, edit)
- Shell execution
- Search / grep
- Web fetch
- Todo management

### Subagents
- Code Review Agent
- Codebase Investigator
- Planner Agent
- Custom subagent support

### Model Support
- Uses OpenAI Python SDK
- Supports any compatible model via model ID
- Auto model selection
- Manual model override

### Safety
- Path-based file restrictions
- Dangerous shell command detection
- Approval policies:
  - `never`
  - `on-request`
  - `auto`
  - `yolo`

### Session Management
- Save & resume sessions
- Checkpoints
- Persistent memory

---
