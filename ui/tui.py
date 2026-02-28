from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.spinner import Spinner
from rich.live import Live
from rich.panel import Panel
from rich import box

AGENT_THEME = Theme({
    # Agent and assistant styles
    "assistant": "bold cyan",
    "user": "bold green",
    "system": "bold yellow",
    "agent": "bold magenta",
    
    # Status and feedback
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "info": "bold blue",
    
    # Agent states
    "thinking": "italic cyan",
    "working": "bold blue",
    "done": "bold green",
    "failed": "bold red",
    
    # Tools and actions
    "tool": "bold yellow",
    "tool.name": "bold bright_yellow",
    "tool.start": "dim yellow",
    "tool.result": "dim green",
    
    # Code and technical
    "code": "bright_white on grey23",
    "command": "bold bright_cyan",
    "path": "underline bright_blue",
    "file": "cyan",
    
    # Subagents
    "subagent": "bold magenta",
    "subagent.ask": "bold bright_cyan",
    "subagent.review": "bold bright_magenta",
    "subagent.plan": "bold bright_yellow",
    
    # UI elements
    "prompt": "bold white",
    "border": "dim white",
    "highlight": "bold bright_white",
    "dim": "dim white",
    
    # Progress and stats
    "progress": "bright_blue",
    "stat.label": "dim cyan",
    "stat.value": "bold white",
    
    # Special
    "checkpoint": "bold bright_green",
    "session": "bold bright_blue",
    "mcp": "bold magenta",
})

_console : Console | None = None
def get_console():
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME)
    return _console


class TUI:
    def __init__(self, console: Console | None = None):
        self.console = console if console else get_console()
        self._assistant_stream_open = False
        self._buffer = "" 
        self._use_markdown = True
        self._last_render_pos = 0 
        self._live_display = None  

    def print_welcome(self, title: str, lines: list[str]) -> None:
        body = "\n".join(lines)
        self.console.print(
            Panel(
                Markdown(body),
                title=Text(title, style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    def show_welcome_message(self) -> None:
        owl_art = """
  ░██████  ░██     ░██ ░████████   ░██████████ ░█████████    ░██████   ░██       ░██ ░██         
 ░██   ░██  ░██   ░██  ░██    ░██  ░██         ░██     ░██  ░██   ░██  ░██       ░██ ░██         
░██          ░██ ░██   ░██    ░██  ░██         ░██     ░██ ░██     ░██ ░██  ░██  ░██ ░██         
░██           ░████    ░████████   ░█████████  ░█████████  ░██     ░██ ░██ ░████ ░██ ░██         
░██            ░██     ░██     ░██ ░██         ░██   ░██   ░██     ░██ ░██░██ ░██░██ ░██         
 ░██   ░██     ░██     ░██     ░██ ░██         ░██    ░██   ░██   ░██  ░████   ░████ ░██         
  ░██████      ░██     ░█████████  ░██████████ ░██     ░██   ░██████   ░███     ░███ ░██████████ 
                                                                                                                                  
   AI Agent CLI
        """
        welcome_md = f"""
{owl_art}

# Welcome to the AI Agent CLI!

Interact with your AI agent in style. Ask questions, give commands, and see responses in real-time.

---

## Quick Start
- Type your message and press Enter to chat with the agent.
- Use `/help` to see available commands.
- Use `/exit` or `/quit` to leave the application.

## Features
- Conversational AI with Markdown and code support
- Tool access for advanced tasks
- Session management and checkpoints
- Live streaming responses

> *Tip: Try asking for code, explanations, or summaries!*
"""
        self.console.print(
            Panel(
                Markdown(welcome_md),
                title=Text("🦉 AI Agent CLI", style="highlight"),
                title_align="left",
                border_style="border",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
    def begin_assistant(self) -> None:
        self.console.print()
        self.console.print(Rule(Text("Assistant", style="assistant")))
        self._assistant_stream_open = True
        self._buffer = ""
        self._last_render_pos = 0
        # Live display is started lazily on first token in stream_assistant_delta

    def end_assistant(self) -> None:
        if self._live_display is not None:
            try:
                self._live_display.stop()
            except Exception:
                pass
            self._live_display = None
        self.console.print()
        self._assistant_stream_open = False
        self._buffer = ""
        self._last_render_pos = 0

    def stream_assistant_delta(self, content: str) -> None:
        self._buffer += content
        if self._live_display is None:
            self.stop_thinking()
            self._live_display = Live(
                Markdown(self._buffer),
                console=self.console,
                refresh_per_second=15,
                transient=False,
                vertical_overflow="visible",
            )
            self._live_display.start()
        else:
            self._live_display.update(Markdown(self._buffer))
    
    def assistant_thinking(self, message: str = "Thinking") -> None:
        """Show an animated thinking/loading indicator"""
        if self._live_display is None:
            spinner = Spinner("dots", text=f"[thinking]{message}...[/]", style="thinking")
            self._live_display = Live(spinner, console=self.console, refresh_per_second=10, transient=True)
            self._live_display.start()
    
    def stop_thinking(self) -> None:
        """Stop the thinking indicator"""
        if self._live_display is not None:
            try:
                self._live_display.stop()
            except Exception:
                pass 
            self._live_display = None
    
    def agent_started(self, agent_name: str, message: str) -> None:
        """Display when agent starts processing"""
        self.console.print(f"[working]▶ Agent started:[/] [dim]{agent_name}[/]")
    
    def agent_finished(self, agent_name: str, response: str | None = None) -> None:
        """Display when agent finishes"""
        if response:
            self.console.print(f"\n[done]✓ Agent finished[/]")
    
    def agent_error(self, message: str) -> None:
        """Display agent errors"""
        self.console.print(f"[error]✗ Error:[/] {message}")
    
    def text_complete(self, content: str) -> None:
        """Display complete text response"""
        pass  # Content already streamed via deltas
    
    def subagent_started(self, subagent_name: str) -> None:
        """Display when a subagent is invoked"""
        style = f"subagent.{subagent_name}" if f"subagent.{subagent_name}" in AGENT_THEME.styles else "subagent"
        self.console.print(f"[{style}]◆ Invoking {subagent_name} subagent[/]")
    
    def info(self, message: str) -> None:
        """Display info message"""
        self.console.print(f"[info]ℹ {message}[/]")
    
    def success(self, message: str) -> None:
        """Display success message"""
        self.console.print(f"[success]✓ {message}[/]")
    
    def warning(self, message: str) -> None:
        """Display warning message"""
        self.console.print(f"[warning]⚠ {message}[/]")

    def show_help(self) -> None:
        help_text = """
## Commands

- `/help` - Show this help
- `/exit` or `/quit` - Exit the agent
- `/clear` - Clear conversation history
- `/config` - Show current configuration
- `/model <name>` - Change the model
- `/approval <mode>` - Change approval mode
- `/stats` - Show session statistics
- `/tools` - List available tools
- `/mcp` - Show MCP server status
- `/save` - Save current session
- `/checkpoint [name]` - Create a checkpoint
- `/checkpoints` - List available checkpoints
- `/restore <checkpoint_id>` - Restore a checkpoint
- `/sessions` - List saved sessions
- `/resume <session_id>` - Resume a saved session

## Tips

- Just type your message to chat with the agent
- The agent can read, write, and execute code
- Some operations require approval (can be configured)
"""
        self.console.print(Markdown(help_text))