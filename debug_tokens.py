#!/usr/bin/env python3
"""Debug script to check token counting accuracy"""
import asyncio
import logging
from pathlib import Path
from config.loader import load_config
from agent.agent import Agent
from lib.text import count_tokens

logging.basicConfig(level=logging.WARN)

async def debug_tokens():
    """Test token counting with a simple agent setup"""
    cwd = Path.cwd()
    config = load_config(cwd)
    
    print("=" * 70)
    print("TOKEN COUNTING DEBUG")
    print("=" * 70)
    print(f"Model: {config.get_model_name}")
    print(f"Context Window: {config.model.context_window:,} tokens")
    print(f"Pruning Budget: {config.pruning.max_window_tokens:,} tokens")
    print()
    
    async with Agent(config) as agent:
        session = agent.session
        
        # Check system prompt size
        system_prompt = session.context_manager.system_prompts
        system_tokens = count_tokens(system_prompt, model=config.get_model_name)
        print(f"System Prompt Size: {len(system_prompt):,} chars")
        print(f"System Prompt Tokens: {system_tokens:,}")
        print()
        
        # Add a simple test message
        test_message = "What is 2 + 2?"
        session.context_manager.add_user_message(test_message)
        user_tokens = count_tokens(test_message, model=config.get_model_name)
        
        print(f"Test Message: '{test_message}'")
        print(f"Test Message Tokens: {user_tokens:,}")
        print()
        
        # Calculate total context
        total_context = system_tokens + user_tokens
        total_pct = (total_context / config.model.context_window) * 100
        
        print(f"Total Context (system + message): {total_context:,} tokens")
        print(f"Percentage of window: {total_pct:.1f}%")
        print()
        
        # Check token counter accuracy
        print("Token Counter Verification:")
        test_texts = [
            ("", 0),
            ("Hello", 1),
            ("Hello world", 2),
            ("The quick brown fox jumps over the lazy dog", 9),
        ]
        
        for text, expected_approx in test_texts:
            tokens = count_tokens(text, model=config.get_model_name)
            print(f"  '{text}' -> {tokens} tokens")
        print()
        
        # Show stats
        stats = session.get_stats()
        print("Session Stats:")
        print(f"  System Prompt Tokens: {stats.get('system_prompt_tokens', 0):,}")
        print(f"  Messages Tokens: {stats.get('messages_tokens', 0):,}")
        print(f"  Current Context: {stats.get('current_context_tokens', 0):,}")
        print(f"  Messages Count: {stats.get('current_messages', 0)}")

if __name__ == "__main__":
    asyncio.run(debug_tokens())
