import time
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

console = Console()

def get_llm_stream():
    """Simulates an LLM response returning tokens one by one."""
    tokens = [
        "# Streaming Markdown\n\n", 
        "This is an **LLM-style** response.\n\n",
        "- Point 1: Fast updates\n", 
        "- Point 2: *Rich* formatting\n\n",
        "```python\nprint('Hello World')\n```"
    ]
    for token in tokens:
        yield token
        time.sleep(0.3)

# Initialize the buffer and Live context
full_response = ""
with Live(Markdown(""), console=console, refresh_per_second=10, vertical_overflow="visible") as live:
    for chunk in get_llm_stream():
        full_response += chunk
        # Re-render the entire accumulated buffer as Markdown
        live.update(Markdown(full_response))
