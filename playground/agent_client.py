#!/usr/bin/env python3
import asyncio
import json
import os
from pathlib import Path
import sys
import base64
from datetime import datetime

import websockets

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.agent import Agent
from agent.events import AgentEventType
from config.loader import load_config

class AgentClient:
    def __init__(self, room_id, agent_name, max_auto_replies=6, mode="cli"):
        self.room_id = room_id
        self.agent_name = agent_name
        self.websocket = None
        self.running = True
        self.max_auto_replies = max_auto_replies
        self.reply_count = 0
        self.mode = mode
        self.e2ee_key = os.getenv("PLAYGROUND_E2EE_KEY", "CLA-PLAYGROUND-SECRET-KEY-2026")

        self.config = None
        self.agent = None

    def _xor_bytes(self, data: bytes) -> bytes:
        key = self.e2ee_key.encode("utf-8")
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    def encrypt(self, text: str) -> str:
        raw = text.encode("utf-8")
        cipher = self._xor_bytes(raw)
        return base64.b64encode(cipher).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            cipher = base64.b64decode(ciphertext.encode("ascii"), validate=True)
            plain = self._xor_bytes(cipher)
            return plain.decode("utf-8")
        except Exception:
            # Backward compatibility: if message is plaintext, pass it through.
            return ciphertext
        
    async def connect(self):
        uri = f"ws://localhost:8000/ws/{self.room_id}/{self.agent_name}"
        print(f"🚀 {self.agent_name} connecting to {uri}")
        
        try:
            self.websocket = await websockets.connect(uri)
            print(f"✅ {self.agent_name} connected!")
            
            # Send join message
            join_msg = {
                'type': 'join',
                'agent': self.agent_name,
                'room': self.room_id,
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }
            await self.websocket.send(json.dumps(join_msg))
            
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    async def _init_real_agent(self):
        if self.mode != "cli":
            return
        try:
            self.config = load_config(ROOT_DIR)
            self.config.cwd = ROOT_DIR
            # Keep chat replies short to reduce noisy loops.
            self.config.max_turns = min(self.config.max_turns, 6)
            self.agent = Agent(self.config)
            await self.agent.__aenter__()
            print("🧠 Real CLI agent mode enabled")
        except Exception as e:
            print(f"⚠️ Could not initialize real CLI agent: {e}")
            print("⚠️ Falling back to mock mode")
            self.mode = "mock"
    
    async def listen(self):
        async for message in self.websocket:
            data = json.loads(message)
            
            if data['type'] == 'system':
                print(f"\n📢 [{data['timestamp']}] SYSTEM: {data['message']}")
            elif data['type'] == 'message':
                decrypted = self.decrypt(data['message']) if data.get('encrypted') else data['message']
                print(f"\n💬 [{data['timestamp']}] {data['sender']}: {decrypted}")
                
                # Simulate agent thinking and responding
                if data.get('sender') != self.agent_name:
                    await self.respond(decrypted, data['sender'])
    
    async def respond(self, received_message, sender):
        if self.reply_count >= self.max_auto_replies:
            return

        await asyncio.sleep(0.65)

        if self.mode == "cli" and self.agent is not None:
            response = await self._respond_with_cli_agent(received_message, sender)
        else:
            response = self._respond_mock(received_message, sender)

        if not response:
            return
        
        self.reply_count += 1
        await self.send_message(response)

    async def _respond_with_cli_agent(self, received_message: str, sender: str) -> str:
        prompt = (
            f"You are {self.agent_name} in room {self.room_id}. "
            f"Message from {sender}: {received_message}\n\n"
            "Focus on natural agent-to-agent dialogue. "
            "Do not write code unless directly requested by another agent. "
            "Reply in 1-4 short sentences and do not use markdown."
        )

        final = ""
        try:
            async for event in self.agent.run(prompt):
                if event.type == AgentEventType.TEXT_COMPLETE:
                    final = event.data.get("content", "").strip()
                elif event.type == AgentEventType.TOOL_STARTED:
                    print(f"🔧 Tool started: {event.data}")
                elif event.type == AgentEventType.TOOL_FINISHED:
                    print(f"✅ Tool completed: {event.data}")
                    # Optionally include tool results in the response
                    tool_result = event.data
                    if tool_result:
                        final += f"\n\n[Tool Result]: {tool_result}"
                elif event.type == AgentEventType.AGENT_ERROR:
                    print(f"⚠️ Agent error: {event.data}")
                    break

      
        


            return final
        except Exception as e:
            print(f"⚠️ Real agent error, switching to mock: {e}")
            self.mode = "mock"
            return self._respond_mock(received_message, sender)

    def _respond_mock(self, received_message: str, sender: str) -> str:
        text = received_message.lower()
        if "hello" in text:
            return f"Hi {sender}! Nice to meet you. How can I help today?"
        if "help" in text:
            return "I'm here to assist. What do you need help with?"
        if "test" in text or "experiment" in text:
            return "This room is useful for agent-to-agent testing and collaboration."
        if "chat" in text:
            return "Ready to chat and collaborate. What should we solve first?"
        return f"I received your message, {sender}. Can you share a bit more detail?"
    
    async def send_message(self, text):
        if not self.websocket:
            return
            
        message = {
            'type': 'message',
            'sender': self.agent_name,
            'room': self.room_id,
            'message': self.encrypt(text),
            'encrypted': True,
            'timestamp': datetime.now().strftime('%H:%M:%S'),
        }
        
        await self.websocket.send(json.dumps(message))
        print(f"\n💬 [{message['timestamp']}] {self.agent_name}: {text}")
    
    async def run(self):
        await self._init_real_agent()

        if not await self.connect():
            return
            
        # Start listening
        listen_task = asyncio.create_task(self.listen())
        
        # Send initial greeting
        await asyncio.sleep(2)
        await self.send_message(f"Hello everyone! I'm {self.agent_name}, ready to collaborate!")
        
        # Keep running
        try:
            await listen_task
        except websockets.ConnectionClosed:
            print(f"❌ {self.agent_name} disconnected")
        finally:
            if self.agent is not None:
                await self.agent.__aexit__(None, None, None)

if __name__ == "__main__":
    if len(sys.argv) < 3 or len(sys.argv) > 5:
        print("Usage: python agent_client.py <room_id> <agent_name> [max_auto_replies] [mode]")
        print("Example: python agent_client.py test-room-001 Agent-CLI-Alpha 8 cli")
        print("Modes: cli (default), mock")
        sys.exit(1)
    
    room_id = sys.argv[1]
    agent_name = sys.argv[2]
    max_replies = int(sys.argv[3]) if len(sys.argv) >= 4 else 6
    mode = sys.argv[4] if len(sys.argv) == 5 else "cli"
    
    client = AgentClient(room_id, agent_name, max_auto_replies=max_replies, mode=mode)
    asyncio.run(client.run())