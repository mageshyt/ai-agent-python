from pathlib import Path
from typing import Any

from rich import console, panel, style
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.spinner import Spinner
from rich.live import Live
from rich.panel import Panel
from rich.table import Table 
from rich import box

from lib.paths import get_relative_path
import re

from lib.text import truncate_text_by_tokens

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
    "muted": "gray50",
    
    # Agent states
    "thinking": "italic cyan",
    "working": "bold blue",
    "done": "bold green",
    "failed": "bold red",
    
    # Tools and actions
    "tool": "bold yellow",
    "tool.name": "bold bright_yellow",
    "tool.read": "cyan",
    "tool.write": "yellow",
    "tool.shell": "magenta",
    "tool.network": "blue",
    "tool.memory": "green",
    "tool.mcp": "bright_cyan",
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
        self._tool_args_by_call_id : dict[str, dict[str, Any]] = {}
        self.cwd = Path.cwd()

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
        self._live_display = Live(
            Spinner("dots", text="[thinking]Thinking...[/]", style="thinking"),
            console=self.console,
            refresh_per_second=15,
            vertical_overflow="visible",
        )
        self._live_display.start()

    def end_assistant(self) -> None:
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self._assistant_stream_open = False
        self._buffer = ""
        self._last_render_pos = 0

    def stream_assistant_delta(self, content: str) -> None:
        self._buffer += content
        if self._live_display is not None:
            self._live_display.update(Markdown(self._buffer))
    
    def assistant_thinking(self, message: str = "Thinking") -> None:
        if self._live_display is not None:
            self._live_display.update(
                Spinner("dots", text=f"[thinking]{message}...[/]", style="thinking")
            )
    
    def stop_thinking(self) -> None:
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
    
    def agent_started(self, agent_name: str, message: str) -> None:
        if self._live_display is not None:
            self._live_display.update(
                Spinner("dots", text=f"[working]▶ {agent_name}...[/]", style="working")
            )
    
    def agent_finished(self, agent_name: str, response: str | None = None) -> None:
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self.console.print()
            
    
    def agent_error(self, message: str) -> None:
        """Display agent errors"""
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self.console.print(f"[error]✗ Error:[/] {message}")
    
    def text_complete(self, content: str) -> None:
        """Display complete text response"""
        pass  # Content already streamed via deltas
    
    def tool_call_started(self, call_id: str, tool_name: str, arguments: dict[str, Any],tool_kind : str) -> None:
        self._tool_args_by_call_id[call_id] = arguments
        border_style = f"tool.{tool_kind}" if f"tool.{tool_kind}" in AGENT_THEME.styles else "tool"
        title = Text.assemble(
                ("▶ ", "muted"),
                (tool_name, "tool"),
                (" ","muted"),
                (f"#{call_id[:8]}", "dim"),
                )

        display_args = dict(arguments)
        for key in ('path','cwd'):
            if key in display_args:
                val = display_args[key]
                # get relative path
                if isinstance(val , str) and self.cwd:
                    display_args[key] = str(get_relative_path(val,self.cwd))
        panel = Panel(
            self._render_args_table(tool_name,display_args) if display_args else Text("No arguments" ),
            title=title,
            title_align="left",
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(1, 2),
            subtitle=Text("running...", style="muted"),
        )
        if self._live_display is not None:
            self._live_display.update(panel)

    def tool_call_finished(self,
       call_id: str,
       tool_name: str,
       tool_kind: str | None,
       success: bool,
       output:str,
       error:str | None = None,
       metadata: dict[str, Any] | None = None,
       truncated: bool = False
    ) -> None:
        border_style = f"tool.{tool_kind}" if tool_kind and f"tool.{tool_kind}" in AGENT_THEME.styles else "tool"
        status_icon = "✓" if success else "✗"
        status_style = "success" if success else "error"
        title = Text.assemble(
                (f"{status_icon} ", status_style),
                (tool_name, "tool"),
                (" ","muted"),
                (f"#{call_id[:8]}", "dim"),
                )
        primary_path = None
        blocks = [] # contain all the blocks to be rendered in the panel

        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = get_relative_path(metadata["path"], self.cwd)

        if tool_name == "read_file" and success:
            start_line, content = self._extract_read_file_content(output) or (0, output)
            show_start = metadata.get("start_line", None)
            show_end = metadata.get("end_line", None)
            total_lines = metadata.get("total_lines", None)
            code_language = self._guess_language(primary_path) if primary_path else None

            header_parts = [primary_path or "file content"]
            header_parts.append(" • ")

            if show_start is not None and show_end is not None and total_lines is not None:
                header_parts.append(f"lines {show_start}-{show_end} of {total_lines}")
            elif total_lines is not None:
                header_parts.append(f"{total_lines} lines")

            header = "".join(header_parts)
            blocks.append(Text(header, style="muted"))
            if code_language:
                blocks.append(Syntax(content, lexer=code_language, word_wrap=True,line_numbers=True, start_line=start_line))
            else:
                output_display = truncate_text_by_tokens(output,250,"")
                blocks.append(Syntax(output_display,"text", word_wrap=False))
        else:             
            content = error if not success and error else output

        if truncated:
            blocks.append(Text("\n[output truncated]", style="muted italic"))
        panel = Panel(
            Group(*blocks) if blocks else Text(content or "No output", style="tool.result"),
            title=title,
            title_align="left",
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(1, 1),
            subtitle=Text("done" if success else "failed", style=status_style),
        )
        if self._live_display is not None:
            self._live_display.update(panel)


        
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
    def _ordered_args(self,tool_name:str,args:dict[str, Any]) -> list[tuple[str,Any]]:
        """
        this funtion helps to show the most important arguments of a tool call first in the TUI. It uses a predefined order for known tools, and then appends any remaining arguments in arbitrary order.
        """
        _PREFERRED_ORDER = {
                'read_file': ['path','offset','limit'],
                "write_file": ["path", "create_directories", "content"],
                "edit": ["path", "replace_all", "old_string", "new_string"],
                "shell": ["command", "timeout", "cwd"],
                "list_dir": ["path", "include_hidden"],
                "grep": ["path", "case_insensitive", "pattern"],
                "glob": ["path", "pattern"],
                "todos": ["id", "action", "content"],
                "memory": ["action", "key", "value"],
        }

        preffered = _PREFERRED_ORDER.get(tool_name, [])
        ordered:list[tuple[str,Any]] = []
        seen = set()

        for key in preffered:
            if key in args:
                ordered.append((key,args[key]))
                seen.add(key)

        remaining_keys =set(args.keys() - seen)
        ordered.extend([(key,args[key]) for key in remaining_keys])
        return ordered

    def _render_args_table(self,tool_name:str,args:dict[str, Any]) -> Table:
        table = Table.grid(padding = (0,1))
        table.add_column(style="muted",justify='right',no_wrap=True)
        table.add_column(style="code", overflow="fold")

        for key, value in self._ordered_args(tool_name,args):
            table.add_row(key, value)
        return table

    def _extract_read_file_content(self,text:str) -> tuple[int,str]|None:
        """
        This function is a helper to extract file content from a tool call output, specifically for read_file tool. It looks for a specific pattern in the text to identify the content and its offset.
        """
        body = text
        header = re.match(r"^Showing lines (\d+) to (\d+) of (\d+)\n\n", text)

        if header:
            # trim down the header
            body = text[header.end():]

        code_lines:list[str] = []
        start_line : int = 0

        for line in body.splitlines():
            # we have reframe the code lines from num|content to just content
            match = re.match(r"^\s*(\d+)\|(.*)$", line)
            if not match:
                return None

            line_num = int(match.group(1))
            if start_line == 0:
                start_line = line_num
            content = match.group(2)
            code_lines.append(content)


        if not code_lines or start_line == 0:
            return None

        return start_line, "\n".join(code_lines)

    def _guess_language(self, path: str | None) -> str:
        if not path:
            return "text"
        suffix = Path(path).suffix.lower()
        return {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "jsx",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".json": "json",
            ".toml": "toml",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".kt": "kotlin",
            ".swift": "swift",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".css": "css",
            ".html": "html",
            ".xml": "xml",
            ".sql": "sql",
        }.get(suffix, "text")
