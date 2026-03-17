import json as _json
import re
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.syntax import Syntax, SyntaxPosition
from rich.theme import Theme
from rich.rule import Rule
from rich.text import Text
from rich.spinner import Spinner
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import box

from config.config import Config
from lib.paths import get_relative_path
from lib.text import truncate_text_by_tokens
from tools.base import FileDiff, ToolKind

# Syntax highlight theme used for all code blocks
CODE_THEME = "monokai"

# Icon used for all tool call starts
TOOL_ICON = "⏺"
TOOL_ICON_SUCCESS = "✓"
TOOL_ICON_ERROR   = "✗"

# Arg keys whose values are too large to display untruncated
_LARGE_VALUE_KEYS = {"content", "old_string", "new_string", "text", "body"}
_MAX_ARG_LEN = 120

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
    "border": "grey35",

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
    def __init__(self, console: Console | None = None,config: Config | None = None) -> None:
        self.console = console if console else get_console()
        self._assistant_stream_open = False
        self._buffer = "" 
        self._use_markdown = True
        self._last_render_pos = 0 
        self._live_display = None  
        self._tool_args_by_call_id : dict[str, dict[str, Any]] = {}
        self.config = config
        self.cwd = config.cwd
        self._max_block_tokens = 2000

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
        owl_art = """  ░██████  ░██     ░██ ░████████   ░██████████ ░█████████    ░██████   ░██       ░██ ░██         
 ░██   ░██  ░██   ░██  ░██    ░██  ░██         ░██     ░██  ░██   ░██  ░██       ░██ ░██         
░██          ░██ ░██   ░██    ░██  ░██         ░██     ░██ ░██     ░██ ░██  ░██  ░██ ░██         
░██           ░████    ░████████   ░█████████  ░█████████  ░██     ░██ ░██ ░████ ░██ ░██         
░██            ░██     ░██     ░██ ░██         ░██   ░██   ░██     ░██ ░██░██ ░██░██ ░██         
 ░██   ░██     ░██     ░██     ░██ ░██         ░██    ░██   ░██   ░██  ░████   ░████ ░██         
  ░██████      ░██     ░█████████  ░██████████ ░██     ░██   ░██████   ░███     ░███ ░██████████"""

        # ASCII banner
        banner = Text(owl_art, style="bold cyan", justify="left")
        self.console.print()
        self.console.print(banner)
        self.console.print()

        # Info grid: model + cwd
        info = Table.grid(padding=(0, 2))
        info.add_column(style="stat.label", no_wrap=True)
        info.add_column(style="stat.value")

        model_name = self.config.get_model_name
        temperature = self.config.get_temperature
        cwd = str(self.config.cwd)

        info.add_row("Model", f"{model_name}  [dim](temp {temperature})[/dim]")
        info.add_row("Directory", cwd)

        self.console.print(
            Panel(
                info,
                border_style="border",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

        # Quick-start hint line
        self.console.print(
            Text.assemble(
                ("  Type your message and press ", "dim"),
                ("Enter", "bold white"),
                (" to chat  ·  ", "dim"),
                ("/help", "command"),
                (" for commands  ·  ", "dim"),
                ("/exit", "command"),
                (" to quit", "dim"),
            )
        )
        self.console.print()
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
            transient=True,
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
        if not self._assistant_stream_open:
            return

        if self._live_display is None:
            self._live_display = Live(
                Markdown(self._buffer) if self._buffer else Spinner("dots", text="[thinking]Thinking...[/]", style="thinking"),
                console=self.console,
                refresh_per_second=15,
                vertical_overflow="visible",
                transient=True,
            )
            self._live_display.start()

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
        self.console.print(Rule(style="border"))
        self.console.print()
            
    
    def agent_error(self, message: str) -> None:
        """Display agent errors"""
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self.console.print(f"[error]✗ Error:[/] {message}")
    
    def text_complete(self, content: str) -> None:
        """Persist the final assistant response for non-tool turns."""
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None

        if not content.strip():
            self._buffer = ""
            return

        if self._use_markdown:
            self.console.print(Markdown(content))
        else:
            self.console.print(Text(content, style="dim white"))

        self._buffer = ""
    
    def tool_call_started(self, call_id: str, tool_name: str, arguments: dict[str, Any], tool_kind: str | ToolKind) -> None:
        self._tool_args_by_call_id[call_id] = arguments

        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None

        if self._buffer.strip():
            if self._use_markdown:
                self.console.print(Markdown(self._buffer.strip()))
            else:
                self.console.print(Text(self._buffer.strip(), style="dim white"))

        # Clear buffered assistant text when entering a tool call so previous
        # planning text is not re-rendered after each tool result.
        self._buffer = ""

        kind_str = tool_kind.value if hasattr(tool_kind, "value") else str(tool_kind)
        border_style = f"tool.{kind_str}" if f"tool.{kind_str}" in AGENT_THEME.styles else "tool"

        title = Text.assemble(
            (f"{TOOL_ICON} ", "muted"),
            (tool_name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )

        display_args = dict(arguments)
        primary_path: str | None = None
        for key in ("path", "cwd"):
            if key in display_args and isinstance(display_args[key], str) and self.cwd:
                display_args[key] = str(get_relative_path(display_args[key], self.cwd))
                if key == "path":
                    primary_path = display_args[key]

        subtitle = Text(primary_path, style="path") if primary_path else Text("running…", style="muted")

        tool_panel = Panel(
            self._render_args_table(tool_name, display_args) if display_args else Text("No arguments", style="muted"),
            title=title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 2),
        )

        self.console.print(tool_panel)

        # Spinner while the tool executes
        self._live_display = Live(
            Spinner("dots", text=f"[{border_style}]{TOOL_ICON} {tool_name} running…[/]"),
            console=self.console,
            refresh_per_second=10,
            vertical_overflow="visible",
        )
        self._live_display.start()

    def tool_call_finished(
        self,
        call_id: str,
        tool_name: str,
        tool_kind: str | None,
        success: bool,
        output: str,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        truncated: bool = False,
        diff: FileDiff | None = None,
        exit_code: int | None = None,
    ) -> None:
        kind_str = tool_kind.value if tool_kind and hasattr(tool_kind, "value") else str(tool_kind or "")
        border_style = f"tool.{kind_str}" if kind_str and f"tool.{kind_str}" in AGENT_THEME.styles else "tool"
        status_icon = TOOL_ICON_SUCCESS if success else TOOL_ICON_ERROR
        status_style = "success" if success else "error"

        title = Text.assemble(
            (f"{status_icon} ", status_style),
            (tool_name, "tool"),
            ("  ", "muted"),
            (f"#{call_id[:8]}", "muted"),
        )
        args = self._tool_args_by_call_id.get(call_id, {})

        primary_path: str | None = None
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = str(get_relative_path(metadata["path"], self.cwd))

        blocks: list = []

        if tool_name == "read_file" and success:
            extracted = self._extract_read_file_content(output)
            start_line, code_content = extracted if extracted else (1, output)
            show_start = metadata.get("start_line") if metadata else None
            show_end   = metadata.get("end_line")   if metadata else None
            total_lines = metadata.get("total_lines") if metadata else None
            code_language = self._guess_language(primary_path) if primary_path else "text"

            # File + range header
            header = Text()
            header.append(primary_path or "file", style="file")
            header.append("  ", style="muted")
            if show_start is not None and show_end is not None:
                header.append(f"lines {show_start}–{show_end}", style="muted")
                if total_lines is not None:
                    header.append(f" of {total_lines}", style="dim")
            elif total_lines is not None:
                header.append(f"{total_lines} lines", style="muted")
            blocks.append(header)
            blocks.append(
                Syntax(
                    code_content,
                    lexer=code_language,
                    theme=CODE_THEME,
                    line_numbers=True,
                    start_line=start_line,
                    word_wrap=False,
                )
            )
        elif tool_name in { "write_file", "edit_file" } and success and diff is not None:
            diff_text = diff.to_diff()
            header = Text()
            header.append(primary_path or "file", style="file")
            header.append("  ", style="muted")
            if diff.is_new_file:
                new_lines = len(diff.new_content.splitlines())
                header.append(f"new file, {new_lines} lines", style="success")
            else:
                old_lines = len(diff.old_content.splitlines())
                new_lines = len(diff.new_content.splitlines())
                delta = new_lines - old_lines
                sign = "+" if delta >= 0 else ""
                header.append(f"{old_lines} → {new_lines} lines ({sign}{delta})", style="muted")
            blocks.append(header)
            if diff_text.strip():
                blocks.append(
                    Syntax(
                        diff_text,
                        lexer="diff",
                        theme=CODE_THEME,
                        word_wrap=False,
                    )
                )
            else:
                blocks.append(Text("(no changes)", style="muted"))
        
        elif tool_name == "shell":
            command = args.get("command", "")

            if command:
                blocks.append(Text(f'$ {command}', style="muted"))

            if exit_code is not None:
                blocks.append(Text(f"Exit code: {exit_code}", style="muted"))
            
            display_output = truncate_text_by_tokens(output,self._max_block_tokens)
            blocks.append(
                    Syntax(
                        display_output,
                        lexer="text",
                        theme=CODE_THEME,
                        word_wrap=False,
                    )
            )

        elif tool_name in "list_dir" and success:
            entries = metadata.get("entries") if isinstance(metadata, dict) else None
            path = metadata.get("path") if isinstance(metadata, dict) else None
            summary = []

            if isinstance(path,str):
                summary.append(str(get_relative_path(path,self.cwd)))
            if isinstance(entries, list):
                summary.append(f"{len(entries)} items")
            if summary:
                blocks.append(Text("  ".join(summary), style="muted"))

            output_display = truncate_text_by_tokens(output,self._max_block_tokens)
            blocks.append(
                    Syntax(
                        output_display,
                        lexer="text",
                        theme=CODE_THEME,
                        word_wrap=False,
                    )
            )

        elif tool_name == "grep" and success:
            files_searched = metadata.get("files_searched") if isinstance(metadata, dict) else None
            files_matched = metadata.get("files_matched") if isinstance(metadata, dict) else None
            summary = []
            if files_searched is not None:
                summary.append(f"{files_searched} files searched")
            if files_matched is not None:
                summary.append(f"{files_matched} matched")
            if summary:
                blocks.append(Text("  ".join(summary), style="muted"))

            output_display = truncate_text_by_tokens(output,self._max_block_tokens)
            blocks.append(
                    Syntax(
                        output_display,
                        lexer="text",
                        theme=CODE_THEME,
                        word_wrap=False,
                    )
            )
        else:
            body = (error or "") if not success else (output or "")
            if body.strip():
                # Try JSON pretty-print
                rendered = False
                if success:
                    try:
                        parsed = _json.loads(body)
                        blocks.append(
                            Syntax(
                                _json.dumps(parsed, indent=2),
                                lexer="json",
                                theme=CODE_THEME,
                                word_wrap=False,
                            )
                        )
                        rendered = True
                    except (ValueError, TypeError):
                        pass
                if not rendered:
                    style = "dim white" if success else "error"
                    blocks.append(Text(body.strip(), style=style))
            else:
                blocks.append(Text("(no output)", style="muted"))

        if truncated:
            blocks.append(Text(" output truncated", style="muted italic"))

        subtitle = Text("done" if success else "failed", style=status_style)
        if primary_path and tool_name != "read_file":
            subtitle = Text(primary_path, style="path")

        result_panel = Panel(
            Group(*blocks),
            title=title,
            title_align="left",
            subtitle=subtitle,
            subtitle_align="right",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1),
        )

        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None

        self.console.print(result_panel)

        # Resume assistant streaming area so subsequent text deltas remain visible.
        if self._assistant_stream_open and self._live_display is None:
            self._buffer = ""
            self._live_display = Live(
                Spinner("dots", text="[thinking]Thinking...[/]", style="thinking"),
                console=self.console,
                refresh_per_second=15,
                vertical_overflow="visible",
                transient=True,
            )
            self._live_display.start()

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
                "edit_file": ["path", "replace_all", "old_string", "new_string"],
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

    def _render_args_table(self, tool_name: str, args: dict[str, Any]) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(overflow="fold")

        for key, value in self._ordered_args(tool_name, args):
            if key in { 'content', 'old_string', 'new_string', 'text', 'body'} and isinstance(value, str):
                line_count = len(value.splitlines()) or 0
                byte_count = len(value.encode('utf-8'))

                value = f"<{line_count} lines, {byte_count} bytes of text>"

            if isinstance(value , bool):
                value = str(value)

            table.add_row(key, self._format_arg_value(key, value))
        return table

    def _format_arg_value(self, key: str, value: Any) -> Text:
        """Render a single argument value with type-aware styling."""
        if isinstance(value, bool):
            return Text(str(value), style="cyan" if value else "muted")
        if isinstance(value, (int, float)):
            return Text(str(value), style="bold bright_white")
        if not isinstance(value, str):
            value = str(value)

        # Decide max length — generous for most keys, short for large content keys
        max_len = 60 if key in _LARGE_VALUE_KEYS else _MAX_ARG_LEN

        # Collapse multiline to single line preview
        lines = value.splitlines()
        if len(lines) > 1:
            preview = lines[0].strip()
            suffix = f"  [{len(lines)} lines]"
        else:
            preview = value
            suffix = ""

        if len(preview) > max_len:
            preview = preview[:max_len - 1] + "…"

        t = Text(preview, style="dim white")
        if suffix:
            t.append(suffix, style="muted")
        return t

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
