#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import random
import base64
from datetime import datetime

import websockets

class SimpleClient:
    def __init__(self, room_id, agent_name):
        self.room_id = room_id
        self.agent_name = agent_name
        self.websocket = None
        self.e2ee_key = os.getenv("PLAYGROUND_E2EE_KEY", "CLA-PLAYGROUND-SECRET-KEY-2026")

    def _xor_bytes(self, data: bytes) -> bytes:
        key = self.e2ee_key.encode("utf-8")
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    def encrypt(self, text: str) -> str:
        return base64.b64encode(self._xor_bytes(text.encode("utf-8"))).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            raw = base64.b64decode(ciphertext.encode("ascii"), validate=True)
            return self._xor_bytes(raw).decode("utf-8")
        except Exception:
            return ciphertext
        
    async def connect(self):
        uri = f"ws://localhost:8000/ws/{self.room_id}/{self.agent_name}"
        print(f"🚀 {self.agent_name} connecting to {uri}")
        
        try:
            self.websocket = await websockets.connect(uri)
            print(f"✅ {self.agent_name} connected!")
            return True
            
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
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
        await asyncio.sleep(random.uniform(1, 3))  # Think time
        
        # Generate response based on content
        if "hello" in received_message.lower():
            response = f"Hi {sender}! Nice to meet you. How can I help today?"
        elif "help" in received_message.lower():
            response = "I'm here to assist! What do you need help with?"
        elif "sandbox" in received_message.lower():
            response = "A sandbox is a safe testing environment. We can experiment freely here!"
        elif "chat" in received_message.lower():
            response = "Chatting is great! What topics interest you?"
        else:
            responses = [
                f"That's interesting, {sender}. Tell me more!",
                f"I see what you mean, {sender}. What do you think about...",
                f"Good point, {sender}. Have you considered...",
                f"Fascinating perspective, {sender}. I'd add that...",
                "Let's explore that idea further. What if...",
                "I'm curious about your thoughts on..."
            ]
            response = random.choice(responses)
        
        await self.send_message(response)
    
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

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python simple_client.py <room_id> <agent_name>")
        print("Example: python simple_client.py test-room-001 Agent-CLI-Alpha")
        sys.exit(1)
    
    room_id = sys.argv[1]
    agent_name = sys.argv[2]
    
    client = SimpleClient(room_id, agent_name)
    asyncio.run(client.run())