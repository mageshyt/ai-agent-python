# CLA Playground Sandbox

This playground lets two local CLI agents join a room and talk to each other over WebSockets.

## What It Simulates

- Shared chat room (`room_id`)
- Multi-agent message exchange
- Local encrypted payload transport (XOR + base64 demo cipher)
- Optional browser monitor UI (`playground/index.html`)

Note: The encryption in this sandbox is only for behavior simulation, not production security.

## Run

From the repo root:

```bash
/Volumes/CodeHub/projects/AI/ai-agent-python/.venv/bin/python playground/server.py
```

In a second terminal:

```bash
/Volumes/CodeHub/projects/AI/ai-agent-python/.venv/bin/python playground/agent_client.py test-room-001 Agent-CLI-Alpha 8
```

In a third terminal:

```bash
/Volumes/CodeHub/projects/AI/ai-agent-python/.venv/bin/python playground/agent_client.py test-room-001 Agent-CLI-Beta 8
```

- The last argument (`8`) is max auto replies.
- Use a bigger number for longer conversations.

## Browser Monitor (Optional)

1. Open `playground/index.html` in a browser.
2. It connects to `ws://localhost:8000/ws/test-room-001`.
3. You can send messages as `Human-Monitor` into the same room.

## Protocol

WebSocket paths:

- `ws://localhost:8000/ws/<room_id>/<agent_id>` for agent clients
- `ws://localhost:8000/ws/<room_id>` for browser monitor

Message shape:

```json
{
  "type": "message",
  "sender": "Agent-CLI-Alpha",
  "room": "test-room-001",
  "message": "<ciphertext>",
  "encrypted": true,
  "timestamp": "12:34:56"
}
```

## Shared Key

Set the same key for all agent terminals (optional):

```bash
export PLAYGROUND_E2EE_KEY="your-shared-key"
```

If unset, defaults to `CLA-PLAYGROUND-SECRET-KEY-2026`.
