#!/usr/bin/env python3
import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import websockets


@dataclass
class ClientInfo:
    room_id: str
    agent_id: str


class PlaygroundServer:
    def __init__(self):
        self.rooms: dict[str, set] = defaultdict(set)
        self.clients: dict = {}

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def _parse_path(path: str) -> tuple[str, str]:
        """
        Supported paths:
        - /ws/<room_id>
        - /ws/<room_id>/<agent_id>
        - /<agent_id> (legacy fallback -> room test-room-001)
        """
        clean = path.strip("/")
        parts = [p for p in clean.split("/") if p]

        if len(parts) >= 2 and parts[0] == "ws":
            room_id = parts[1]
            agent_id = parts[2] if len(parts) >= 3 else "human-monitor"
            return room_id, agent_id

        if len(parts) == 1:
            return "test-room-001", parts[0]

        return "test-room-001", "anonymous"

    async def _send_system(self, websocket, text: str):
        payload = {
            "type": "system",
            "message": text,
            "timestamp": self._ts(),
        }
        await websocket.send(json.dumps(payload))

    async def _broadcast(self, room_id: str, payload: dict, sender_ws=None):
        data = json.dumps(payload)
        dead = []

        for ws in self.rooms.get(room_id, set()):
            if sender_ws is not None and ws is sender_ws:
                continue
            try:
                await ws.send(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self._disconnect(ws)

    async def _disconnect(self, websocket):
        info = self.clients.pop(websocket, None)
        if info is None:
            return

        room = self.rooms.get(info.room_id)
        if room and websocket in room:
            room.remove(websocket)

        if room is not None and len(room) == 0:
            del self.rooms[info.room_id]

        await self._broadcast(
            info.room_id,
            {
                "type": "system",
                "message": f"{info.agent_id} left room {info.room_id}",
                "timestamp": self._ts(),
            },
            sender_ws=websocket,
        )
        print(f"[disconnect] room={info.room_id} agent={info.agent_id}")

    async def handler(self, websocket):
        path = urlparse(websocket.request.path).path
        room_id, agent_id = self._parse_path(path)

        self.rooms[room_id].add(websocket)
        self.clients[websocket] = ClientInfo(room_id=room_id, agent_id=agent_id)
        print(f"[connect] room={room_id} agent={agent_id} path={path}")

        await self._send_system(
            websocket,
            f"Welcome {agent_id}. Room={room_id}. Others online={len(self.rooms[room_id]) - 1}",
        )

        await self._broadcast(
            room_id,
            {
                "type": "system",
                "message": f"{agent_id} joined room {room_id}",
                "timestamp": self._ts(),
            },
            sender_ws=websocket,
        )

        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send_system(websocket, "Invalid JSON message ignored.")
                    continue

                msg_type = data.get("type")
                if msg_type == "join":
                    # Optional client hello; ignore silently for compatibility.
                    continue

                if msg_type != "message":
                    await self._send_system(websocket, f"Unknown message type: {msg_type}")
                    continue

                sender = data.get("sender") or agent_id
                outbound = {
                    "type": "message",
                    "sender": sender,
                    "room": room_id,
                    "message": data.get("message", ""),
                    "encrypted": bool(data.get("encrypted", False)),
                    "timestamp": self._ts(),
                }
                await self._broadcast(room_id, outbound, sender_ws=websocket)

        except websockets.ConnectionClosed:
            pass
        finally:
            await self._disconnect(websocket)


async def main():
    server = PlaygroundServer()

    async with websockets.serve(server.handler, "localhost", 8000):
        print("CLA Playground server running at ws://localhost:8000")
        print("Paths:")
        print("  - ws://localhost:8000/ws/test-room-001/Agent-CLI-Alpha")
        print("  - ws://localhost:8000/ws/test-room-001/Agent-CLI-Beta")
        print("  - ws://localhost:8000/ws/test-room-001 (browser monitor)")
        print("Press Ctrl+C to stop.")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())