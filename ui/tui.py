from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text

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

    def begin_assistant(self) -> None:
        self.console.print()
        self.console.print(Rule(Text("Assistant", style="assistant")))
        self._assistant_stream_open = True
        self._buffer = ""

    def end_assistant(self) -> None:
        if self._assistant_stream_open:
            if self._use_markdown and self._buffer:
                # Render buffered content as markdown
                self.console.print(Markdown(self._buffer))
            self.console.print()
        self._assistant_stream_open = False
        self._buffer = ""

    def stream_assistant_delta(self, content: str) -> None:
        if self._use_markdown:
            self._buffer += content
        else:
            self.console.print(content, end="", markup=True, highlight=True, emoji=True)
    
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


