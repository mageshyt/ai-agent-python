import json as _json
import importlib
import random
import re
import time
import asyncio
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.theme import Theme
from rich.text import Text
from rich.spinner import Spinner
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich import box

from config.config import Config
from lib.contants.config import AGENT_ASCII_FONT, AGENT_DISPLAY_NAME, AGENT_TAGLINE
from lib.paths import get_relative_path
from lib.text import truncate_text_by_tokens
from lib.contants.figures import (
    BLACK_CIRCLE,
    BLOCKQUOTE_BAR,
    BULLET_OPERATOR,
    DIAMOND_FILLED,
    DIAMOND_OPEN,
    HEAVY_HORIZONTAL,
    PLAY_ICON,
    TEARDROP_ASTERISK,
)
from tools.base import FileDiff, ToolKind

# -- Import SPINNER_VERBS (handle hyphenated module name gracefully) ------
try:
    _spinner_mod = importlib.import_module("lib.contants.spinner-verbs")
    SPINNER_VERBS: list[str] = getattr(_spinner_mod, "SPINNER_VERBS", ["Thinking"])
except Exception:
    SPINNER_VERBS: list[str] = ["Thinking"]

# Syntax highlight theme used for all code blocks
CODE_THEME = "monokai"

# Icons from figures.py
TOOL_ICON = BLACK_CIRCLE         # ⏺ tool call indicator
TOOL_ICON_SUCCESS = DIAMOND_FILLED  # ◆ completed
TOOL_ICON_ERROR   = "✗"          # failure
TOOL_RUNNING = DIAMOND_OPEN      # ◇ running
ASSISTANT_ICON = TEARDROP_ASTERISK  # ✻ assistant reply indicator
AGENT_PLAY = PLAY_ICON           # ▶ agent started
SEPARATOR = BULLET_OPERATOR      # ∙ separator

# Left bar character used for indented output (Claude Code style)
LEFT_BAR = BLOCKQUOTE_BAR
RULE_CHAR = HEAVY_HORIZONTAL

# Arg keys whose values are too large to display untruncated
_LARGE_VALUE_KEYS = {"content", "old_string", "new_string", "text", "body"}
_MAX_ARG_LEN = 120

# ─── Cyan / Teal color palette ────────────────────────────────────────────
AGENT_THEME = Theme({
    # Agent and assistant styles
    "assistant": "bold #22d3ee",
    "user": "bold green",
    "system": "bold yellow",
    "agent": "bold #06b6d4",

    # Status and feedback
    "success": "bold #86efac",
    "error": "bold #f87171",
    "warning": "bold #fbbf24",
    "info": "bold #67e8f9",
    "muted": "gray50",

    # Agent states
    "thinking": "italic #67e8f9",
    "working": "bold #22d3ee",
    "done": "bold #86efac",
    "failed": "bold #f87171",

    # Tools and actions
    "tool": "bold #0891b2",
    "tool.name": "bold #cffafe",
    "tool.read": "#67e8f9",
    "tool.write": "#fbbf24",
    "tool.shell": "#22d3ee",
    "tool.network": "#38bdf8",
    "tool.memory": "#86efac",
    "tool.mcp": "#67e8f9",
    "tool.start": "dim #67e8f9",
    "tool.result": "dim #86efac",

    # Code and technical
    "code": "bright_white on grey23",
    "command": "bold #22d3ee",
    "path": "underline #67e8f9",
    "file": "#a5f3fc",

    # Subagents
    "subagent": "bold #0891b2",
    "subagent.ask": "bold #67e8f9",
    "subagent.review": "bold #22d3ee",
    "subagent.plan": "bold #cffafe",

    # UI elements
    "prompt": "bold #22d3ee",
    "border": "#155e75",
    "highlight": "bold bright_white",
    "dim": "dim white",

    # Left bar for Claude-style output blocks
    "leftbar": "#0891b2",
    "leftbar.success": "#86efac",
    "leftbar.error": "#f87171",

    # Progress and stats
    "progress": "#67e8f9",
    "stat.label": "dim #a5f3fc",
    "stat.value": "bold white",

    # Special
    "checkpoint": "bold #86efac",
    "session": "bold #67e8f9",
    "mcp": "bold #0891b2",
})

_console: Console | None = None
def get_console():
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME)
    return _console


def _random_verb() -> str:
    """Pick a random spinner verb from the fun list."""
    return random.choice(SPINNER_VERBS)


class TUI:
    def __init__(self, console: Console | None = None, config: Config | None = None) -> None:
        self.console = console if console else get_console()
        self._assistant_stream_open = False
        self._buffer = ""
        self._use_markdown = True
        self._live_display = None
        self._verb_task: asyncio.Task | None = None
        self._spinner_style: str = "thinking"      # current spinner style
        self._spinner_prefix: str = ""              # e.g. "▶ AgentName ∙ "
        self._is_streaming_text: bool = False       # True while text deltas arrive
        self._tool_args_by_call_id: dict[str, dict[str, Any]] = {}
        self.config = config
        self.cwd = config.cwd
        self._max_block_tokens = 2000

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _start_verb_rotation(self, style: str = "thinking", prefix: str = "", interval: float = 2.0) -> None:
        """Start a repeating async task that cycles the spinner verb every `interval` seconds."""
        self._stop_verb_rotation()  # cancel any existing task
        self._spinner_style = style
        self._spinner_prefix = prefix

        async def _run():
            try:
                while True:
                    if self._live_display is not None and self._buffer == "" and not self._is_streaming_text:
                        verb = _random_verb()
                        try:
                            self._live_display.update(
                                Spinner("dots", text=f"[{self._spinner_style}]{self._spinner_prefix}{verb}...[/]", style=self._spinner_style)
                            )
                        except Exception:
                            # Live may have been stopped between ticks
                            pass
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                return

        try:
            loop = asyncio.get_running_loop()
            self._verb_task = loop.create_task(_run())
        except RuntimeError:
            # No running loop; run a background loop briefly (fallback)
            self._verb_task = asyncio.create_task(_run())

    def _stop_verb_rotation(self) -> None:
        """Cancel the verb rotation task."""
        task = getattr(self, "_verb_task", None)
        if task is not None:
            task.cancel()
            self._verb_task = None

    def _left_bar_renderable(self, renderable, style: str = "leftbar"):
        """Wrap a Rich renderable with a left-border-only panel.
        
        Uses HEAVY_HEAD box customization so only the left edge shows the bar.
        """
        # Create a custom box that only shows the left border
        LEFT_ONLY = box.Box(
            "    \n"
            f"{LEFT_BAR}   \n"
            "    \n"
            f"{LEFT_BAR}   \n"
            f"{LEFT_BAR}   \n"
            "    \n"
            f"{LEFT_BAR}   \n"
            "    \n"
        )
        return Panel(
            renderable,
            border_style=style,
            box=LEFT_ONLY,
            padding=(0, 1),
            expand=True,
        )

    def _compact_rule(self) -> Rule:
        """A thin horizontal rule."""
        return Rule(style="border", characters=RULE_CHAR)

    def _code_panel(self, syntax: Syntax, title: str = "", subtitle: str = "") -> Panel:
        """Wrap a Syntax block in a modern rounded-border panel."""
        title_text = Text(f" {title} ", style="file") if title else None
        subtitle_text = Text(f" {subtitle} ", style="muted") if subtitle else None
        return Panel(
            syntax,
            title=title_text,
            title_align="left",
            subtitle=subtitle_text,
            subtitle_align="right",
            border_style="border",
            box=box.ROUNDED,
            padding=(0, 1),
            expand=True,
        )

    # ─── Welcome / Banner ─────────────────────────────────────────────────

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
        owl_art = self._build_ascii_banner(AGENT_DISPLAY_NAME)

        # Startup animation with a random verb
        with self.console.status(f"[working]{_random_verb()}...[/]", spinner="dots"):
            time.sleep(0.25)

        # ASCII banner with gradient
        banner = self._gradient_text(
            owl_art,
            start=(8, 145, 178),    # dark cyan #0891b2
            end=(103, 232, 249),    # light cyan #67e8f9
            bold=True,
        )
        self.console.print()
        self.console.print(banner)
        self.console.print()

        # Info grid: model + cwd (compact, no panel)
        info = Table.grid(padding=(0, 2))
        info.add_column(style="stat.label", no_wrap=True)
        info.add_column(style="stat.value")

        model_name = self.config.get_model_name
        temperature = self.config.get_temperature
        cwd = str(self.config.cwd)

        info.add_row("Model", f"{model_name}  [dim](temp {temperature})[/dim]")
        info.add_row("Directory", cwd)

        self.console.print(info)
        self.console.print()

        # Quick-start hint line
        self.console.print(
            Text.assemble(
                ("  Type a message or ", "dim"),
                ("/help", "command"),
                (" for commands", "dim"),
            )
        )
        self.console.print()

    def _build_ascii_banner(self, title: str) -> str:
        """Build ASCII title text with pyfiglet if available, else fallback art."""
        try:
            pyfiglet = importlib.import_module("pyfiglet")
            Figlet = getattr(pyfiglet, "Figlet")
            figlet = Figlet(font=AGENT_ASCII_FONT)
            return figlet.renderText(title).rstrip("\n")
        except Exception:
            return """  ░██████  ░██     ░██ ░████████   ░██████████ ░█████████    ░██████   ░██       ░██ ░██         
 ░██   ░██  ░██   ░██  ░██    ░██  ░██         ░██     ░██  ░██   ░██  ░██       ░██ ░██         
░██          ░██ ░██   ░██    ░██  ░██         ░██     ░██ ░██     ░██ ░██  ░██  ░██ ░██         
░██           ░████    ░████████   ░█████████  ░█████████  ░██     ░██ ░██ ░████ ░██ ░██         
░██            ░██     ░██     ░██ ░██         ░██   ░██   ░██     ░██ ░██░██ ░██░██ ░██         
 ░██   ░██     ░██     ░██     ░██ ░██         ░██    ░██   ░██   ░██  ░████   ░████ ░██         
  ░██████      ░██     ░█████████  ░██████████ ░██     ░██   ░██████   ░███     ░███ ░██████████"""

    def _gradient_text(self, text: str, start: tuple[int, int, int], end: tuple[int, int, int], bold: bool = False) -> Text:
        """Render multiline text with a left-to-right RGB gradient."""
        lines = text.splitlines()
        visible_chars = sum(1 for ch in text if ch not in {"\n", " "})
        if visible_chars <= 1:
            return Text(text, style="bold #22d3ee" if bold else "#22d3ee")

        out = Text()
        idx = 0
        for line_no, line in enumerate(lines):
            for ch in line:
                if ch == " ":
                    out.append(ch)
                    continue

                ratio = idx / (visible_chars - 1)
                r = int(start[0] + (end[0] - start[0]) * ratio)
                g = int(start[1] + (end[1] - start[1]) * ratio)
                b = int(start[2] + (end[2] - start[2]) * ratio)
                style = f"#{r:02x}{g:02x}{b:02x}"
                if bold:
                    style += " bold"
                out.append(ch, style=style)
                idx += 1

            if line_no < len(lines) - 1:
                out.append("\n")

        return out

    # ─── Assistant Streaming ──────────────────────────────────────────────

    def begin_assistant(self) -> None:
        self.console.print()
        self._assistant_stream_open = True
        self._buffer = ""
        verb = _random_verb()
        self._live_display = Live(
            Spinner("dots", text=f"[thinking]{verb}...[/]", style="thinking"),
            console=self.console,
            refresh_per_second=12,
            vertical_overflow="visible",
            transient=True,
        )
        self._live_display.start()
        self._start_verb_rotation(style="thinking")

    def end_assistant(self) -> None:
        self._stop_verb_rotation()
        self._is_streaming_text = False
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self._assistant_stream_open = False
        self._buffer = ""

    def stream_assistant_delta(self, content: str) -> None:
        self._buffer += content
        if not self._assistant_stream_open:
            return

        if self._live_display is not None:
            self._stop_verb_rotation()  # stop rotating once text starts streaming
            self._is_streaming_text = True
            grp_msg = Group(
                Text(ASSISTANT_ICON, style="assistant",end=" "),
                Markdown(self._buffer)
            )
            try:
                self._live_display.update(grp_msg)
            except Exception:
                pass

    def assistant_thinking(self, message: str = "Thinking") -> None:
        verb = _random_verb()
        if self._live_display is not None:
            try:
                self._live_display.update(
                    Spinner("dots", text=f"[thinking]{verb}...[/]", style="thinking")
                )
            except Exception:
                pass
            self._start_verb_rotation(style="thinking")

    def stop_thinking(self) -> None:
        self._stop_verb_rotation()
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None

    def agent_started(self, agent_name: str, message: str) -> None:
        if self._live_display is not None:
            verb = _random_verb()
            try:
                self._live_display.update(
                    Spinner("dots", text=f"[working]{AGENT_PLAY} {agent_name} {SEPARATOR} {verb}...[/]", style="working")
                )
            except Exception:
                pass
            self._start_verb_rotation(style="working", prefix=f"{AGENT_PLAY} {agent_name} {SEPARATOR} ")

    def agent_finished(self, agent_name: str, response: str | None = None) -> None:
        self._stop_verb_rotation()
        if self._assistant_stream_open and self._live_display is not None:
            # Sub-agent done but assistant turn continues — switch back to thinking spinner
            self._live_display.update(
                Spinner("dots", text=f"[thinking]{_random_verb()}...[/]", style="thinking")
            )
            self._start_verb_rotation(style="thinking")
        elif self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self.console.print()

    def agent_error(self, message: str) -> None:
        """Display agent errors"""
        self._stop_verb_rotation()
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None
        self.console.print(
            Text.assemble(
                (f"  {TOOL_ICON_ERROR} ", "error"),
                ("Error: ", "error"),
                (message, "dim white"),
            )
        )

    # ─── Assistant Final Text ─────────────────────────────────────────────

    def text_complete(self, content: str) -> None:
        """Persist the final assistant response with ✻ prefix."""
        self._stop_verb_rotation()
        if self._live_display is not None:
            self._live_display.stop()
            self._live_display = None

        if not content.strip():
            self._buffer = ""
            return

        if self._use_markdown:
            # Prepend ✻ into the markdown so it renders inline
            grp_msg = Group(
                Text(ASSISTANT_ICON, style="assistant",end=" "),
                Markdown(content)
            )
            self.console.print(grp_msg)
        else:
            self.console.print(
                Text.assemble(
                    (f"{ASSISTANT_ICON} ", "assistant"),
                    (content.strip(), "dim white"),
                )
            )

        self._buffer = ""

    # ─── Tool Calls — Compact Claude Code Style ──────────────────────────

    def tool_call_started(self, call_id: str, tool_name: str, arguments: dict[str, Any], tool_kind: str | ToolKind) -> None:
        self._tool_args_by_call_id[call_id] = arguments

        self._stop_verb_rotation()
        self._is_streaming_text = False

        # Clear Live content to avoid duplication when flushing buffer
        if self._live_display is not None:
            self._live_display.update(Text(""))

        if self._buffer.strip():
            if self._use_markdown:
                grp_msg = Group(
                    Text(ASSISTANT_ICON, style="assistant", end=" "),
                    Markdown(self._buffer.strip())
                )
                self.console.print(grp_msg)
            else:
                self.console.print(Text(self._buffer.strip(), style="dim white"))

        # Clear buffered assistant text
        self._buffer = ""

        kind_str = tool_kind.value if hasattr(tool_kind, "value") else str(tool_kind)
        tool_style = f"tool.{kind_str}" if f"tool.{kind_str}" in AGENT_THEME.styles else "tool"

        # === Compact header line: ⏺ tool_name ===
        header = Text()
        header.append(f"  {TOOL_ICON} ", style=tool_style)
        header.append(tool_name, style="tool.name")

        # Show primary arg inline on the header line
        display_args = dict(arguments)
        primary_path: str | None = None
        for key in ("path", "cwd"):
            if key in display_args and isinstance(display_args[key], str) and self.cwd:
                display_args[key] = str(get_relative_path(display_args[key], self.cwd))
                if key == "path":
                    primary_path = display_args[key]

        if primary_path:
            header.append(f" {SEPARATOR} ", style="muted")
            header.append(primary_path, style="path")

        self.console.print(header)

        # === Indented args with left bar ===
        if display_args:
            args_table = self._render_args_table(tool_name, display_args)
            self.console.print(
                self._left_bar_renderable(args_table, style=tool_style)
            )

        # Update spinner while the tool executes (reuse existing Live)
        verb = _random_verb()
        spinner = Spinner("dots", text=f"[{tool_style}]  {LEFT_BAR} {verb}...[/]")
        if self._live_display is not None:
            self._live_display.update(spinner)
        else:
            self._live_display = Live(
                spinner,
                console=self.console,
                refresh_per_second=12,
                vertical_overflow="visible",
                transient=True,
            )
            self._live_display.start()
        self._start_verb_rotation(style=tool_style, prefix=f"  {LEFT_BAR} ")

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
        tool_style = f"tool.{kind_str}" if kind_str and f"tool.{kind_str}" in AGENT_THEME.styles else "tool"

        args = self._tool_args_by_call_id.get(call_id, {})

        primary_path: str | None = None
        if isinstance(metadata, dict) and isinstance(metadata.get("path"), str):
            primary_path = str(get_relative_path(metadata["path"], self.cwd))

        blocks: list = []

        if tool_name == "read_file" and success:
            # If tool opted not to include content, show a compact summary only
            if isinstance(metadata, dict) and metadata.get("show_file") is False:
                path_text = primary_path or (metadata.get("path") if isinstance(metadata.get("path"), str) else "file")
                show_start = metadata.get("start_line") if metadata else None
                show_end   = metadata.get("end_line")   if metadata else None
                total_lines = metadata.get("total_lines") if metadata else None

                summary_parts = [path_text]
                if show_start is not None and show_end is not None:
                    part = f"lines {show_start}–{show_end}"
                    if total_lines is not None:
                        part += f" of {total_lines}"
                    summary_parts.append(part)
                elif total_lines is not None:
                    summary_parts.append(f"{total_lines} lines")
                blocks.append(Text("  ".join(summary_parts), style="muted"))
            else:
                extracted = self._extract_read_file_content(output)
                start_line, code_content = extracted if extracted else (1, output)
                show_start = metadata.get("start_line") if metadata else None
                show_end   = metadata.get("end_line")   if metadata else None
                total_lines = metadata.get("total_lines") if metadata else None
                code_language = self._guess_language(primary_path) if primary_path else "text"
                line_count = len(code_content.splitlines())

                # Build title: "filename.py" and subtitle: "lines 1-50 of 200"
                panel_title = primary_path or "file"
                subtitle_parts = []
                if show_start is not None and show_end is not None:
                    subtitle_parts.append(f"lines {show_start}–{show_end}")
                    if total_lines is not None:
                        subtitle_parts.append(f"of {total_lines}")
                elif total_lines is not None:
                    subtitle_parts.append(f"{total_lines} lines")
                subtitle_parts.append(f"{line_count} lines read")
                panel_subtitle = "  ".join(subtitle_parts)

                # Show max 20 lines preview, collapse the rest
                MAX_PREVIEW_LINES = 20
                preview_lines = code_content.splitlines()
                if len(preview_lines) > MAX_PREVIEW_LINES:
                    preview_content = "\n".join(preview_lines[:MAX_PREVIEW_LINES])
                    remaining = len(preview_lines) - MAX_PREVIEW_LINES
                    blocks.append(
                        self._code_panel(
                            Syntax(preview_content, lexer=code_language, theme=CODE_THEME, line_numbers=True, start_line=start_line, word_wrap=False),
                            title=panel_title,
                            subtitle=panel_subtitle,
                        )
                    )
                    blocks.append(Text(f"  ... {remaining} more lines (truncated)", style="muted italic"))
                else:
                    blocks.append(
                        self._code_panel(
                            Syntax(code_content, lexer=code_language, theme=CODE_THEME, line_numbers=True, start_line=start_line, word_wrap=False),
                            title=panel_title,
                            subtitle=panel_subtitle,
                        )
                    )
        elif tool_name in {"write_file", "edit_file"} and success and diff is not None:
            diff_text = diff.to_diff()
            # Build subtitle with change stats
            if diff.is_new_file:
                new_lines = len(diff.new_content.splitlines())
                subtitle = f"new file  {new_lines} lines"
            else:
                old_lines = len(diff.old_content.splitlines())
                new_lines = len(diff.new_content.splitlines())
                delta = new_lines - old_lines
                sign = "+" if delta >= 0 else ""
                subtitle = f"{old_lines} → {new_lines} lines ({sign}{delta})"

            if diff_text.strip():
                blocks.append(
                    self._code_panel(
                        Syntax(diff_text, lexer="diff", theme=CODE_THEME, word_wrap=False),
                        title=primary_path or "file",
                        subtitle=subtitle,
                    )
                )
            else:
                blocks.append(Text("(no changes)", style="muted"))

        elif tool_name == "shell":
            command = args.get("command", "")
            shell_subtitle = ""
            if exit_code is not None:
                shell_subtitle = f"exit {exit_code}"

            display_output = truncate_text_by_tokens(output, self._max_block_tokens)
            blocks.append(
                self._code_panel(
                    Syntax(display_output, lexer="text", theme=CODE_THEME, word_wrap=False),
                    title=f"$ {command}" if command else "shell",
                    subtitle=shell_subtitle,
                )
            )

        elif tool_name == "list_dir" and success:
            entries = metadata.get("entries") if isinstance(metadata, dict) else None
            path = metadata.get("path") if isinstance(metadata, dict) else None
            summary = []

            if isinstance(path, str):
                summary.append(str(get_relative_path(path, self.cwd)))
            if isinstance(entries, list):
                summary.append(f"{len(entries)} items")
            if summary:
                blocks.append(Text("  ".join(summary), style="muted"))

            output_display = truncate_text_by_tokens(output, self._max_block_tokens)

            # Custom formatting for list_dir output
            list_text = Text()
            for line in output_display.splitlines():
                if not line:
                    continue

            # Match tree prefixes (e.g. "├── ", "│   ", "└── ")
                tree_match = re.match(r"^([│ \t├─└]+)(.*)$", line)
                if tree_match:
                    prefix, name = tree_match.groups()
                    list_text.append(prefix, style="dim")

                    if "[ignored]" in name:
                        list_text.append(name, style="muted")
                    elif name.endswith("/"):
                        list_text.append(name, style="path")
                    else:
                        list_text.append(name, style="file")
                    list_text.append("\n")
                else:
                    # Top level directory name
                    if line.endswith("/"):
                        list_text.append(line + "\n", style="path")
                    else:
                        list_text.append(line + "\n", style="file")

            blocks.append(list_text)

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

            output_display = truncate_text_by_tokens(output, self._max_block_tokens)

            # Custom formatting for grep output
            grep_text = Text()
            for line in output_display.splitlines():
                if not line.strip():
                    grep_text.append("\n")
                    continue

                parts = line.split(":", 2)
                if len(parts) >= 3 and parts[1].isdigit():
                    file_path, line_num, content = parts[0], parts[1], parts[2]
                    grep_text.append(file_path, style="path")
                    grep_text.append(":", style="dim")
                    grep_text.append(line_num, style="success")
                    grep_text.append(":", style="dim")
                    grep_text.append(f" {content}\n", style="dim white")
                else:
                    grep_text.append(line + "\n", style="dim white")

            blocks.append(grep_text)

        elif tool_name == "glob" and success:
            files_matched = metadata.get("files_matched", 0) if isinstance(metadata, dict) else 0
            pattern = metadata.get("pattern", "") if isinstance(metadata, dict) else ""

            summary = []
            if pattern:
                summary.append(f"Pattern: '{pattern}'")
            if files_matched is not None:
                summary.append(f"({files_matched} matches)")

            if summary:
                blocks.append(Text("  ".join(summary), style="muted"))

            output_display = truncate_text_by_tokens(output, self._max_block_tokens)

            glob_text = Text()
            for line in output_display.splitlines():
                if not line.strip():
                    continue
                if line.startswith("Output truncated"):
                    glob_text.append(f"\n{line}\n", style="warning")
                else:
                    glob_text.append("• ", style="dim")
                    glob_text.append(f"{line}\n", style="file")

            blocks.append(glob_text)

        elif tool_name == "web_search" and success:
            query = metadata.get("query", "") if isinstance(metadata, dict) else ""
            results = metadata.get("results", []) if isinstance(metadata, dict) else []

            if query:
                blocks.append(Text(f"Search query: {query}", style="muted"))

            if results:
                for i, res in enumerate(results):
                    title = res.get("title", "No Title")
                    url = res.get("url", "")
                    desc = res.get("description", "")

                    item = Text()
                    item.append(f"{i+1}. ", style="bold #67e8f9")
                    item.append(f"{title}\n", style="bold white")
                    item.append(f"   {url}\n", style="#a5f3fc")

                    clean_desc = " ".join(desc.split())
                    item.append(f"   {clean_desc}", style="dim white")

                    blocks.append(item)
            else:
                blocks.append(Text("No results found.", style="muted"))

        elif tool_name == "web_scrap" and success:
            url = metadata.get("url", args.get("url", "")) if isinstance(metadata, dict) else args.get("url", "")
            status_code = metadata.get("status_code") if isinstance(metadata, dict) else None
            out_len = len(output)

            # Build subtitle with status and length
            subtitle_parts = []
            if status_code is not None:
                icon = TOOL_ICON_SUCCESS if 200 <= status_code < 300 else TOOL_ICON_ERROR
                subtitle_parts.append(f"{status_code} {icon}")
            subtitle_parts.append(f"{out_len} chars")
            if truncated:
                subtitle_parts.append("truncated")

            output_display = truncate_text_by_tokens(output, self._max_block_tokens)

            blocks.append(
                self._code_panel(
                    Syntax(output_display, lexer="html", theme=CODE_THEME, word_wrap=False),
                    title=url or "web",
                    subtitle="  ".join(subtitle_parts),
                )
            )

        elif tool_name == "todos" and success:
            action = args.get("action", "")

            summary = []
            if action:
                summary.append(f"Action: {action.capitalize()}")
            if summary:
                blocks.append(Text("  ".join(summary), style="muted"))

            output_display = truncate_text_by_tokens(output, self._max_block_tokens)

            if action == "list" and "No todo items found" not in output_display:
                todo_text = Text()
                for line in output_display.splitlines():
                    if not line.strip():
                        continue
                    if line.startswith("✓"):
                        todo_text.append("[✓] ", style="success")
                        todo_text.append(line[2:] + "\n", style="bold white")
                    elif line.startswith("✗"):
                        todo_text.append("[✗] ", style="warning")
                        todo_text.append(line[2:] + "\n", style="dim white")
                    else:
                        todo_text.append(line + "\n", style="dim white")

                blocks.append(todo_text)
            else:
                blocks.append(Text(output_display, style="dim white"))

        elif tool_name == "memory" and success:
            action = args.get("action", "")
            key = args.get("key", "")

            mem_title = f"memory:{key}" if key else "memory"
            mem_subtitle = action.capitalize() if isinstance(action, str) and action else ""
            lexer = "json" if action == "get" else "text"

            output_display = truncate_text_by_tokens(output, self._max_block_tokens)

            blocks.append(
                self._code_panel(
                    Syntax(output_display, lexer=lexer, theme=CODE_THEME, word_wrap=False),
                    title=mem_title,
                    subtitle=mem_subtitle,
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

        self._stop_verb_rotation()

        # Clear spinner so static content prints cleanly
        if self._live_display is not None:
            self._live_display.update(Text(""))

        # === Print output with left bar (Claude Code style — no status line) ===
        if blocks:
            self.console.print(
                self._left_bar_renderable(Group(*blocks), style=tool_style)
            )

        # Resume assistant streaming area (reuse existing Live)
        if self._assistant_stream_open:
            verb = _random_verb()
            spinner = Spinner("dots", text=f"[thinking]{verb}...[/]", style="thinking")
            if self._live_display is not None:
                self._live_display.update(spinner)
            else:
                self._live_display = Live(
                    spinner,
                    console=self.console,
                    refresh_per_second=12,
                    vertical_overflow="visible",
                    transient=True,
                )
                self._live_display.start()
            self._start_verb_rotation(style="thinking")
        elif self._live_display is not None:
            self._live_display.stop()
            self._live_display = None

    def compaction_started(self ) -> None:
        """Display when context compaction is started."""
        self._stop_verb_rotation()
        self._is_streaming_text = False

        if self._live_display is not None:
            try:
                self._live_display.update(
                    Spinner("dots", text=f"[working]Compacting context...[/]", style="working")
                )
            except Exception:
                pass

    def compaction_finished(
        self,
        summary: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        """Display when context compaction is finished."""
        self._stop_verb_rotation()

        usage_text = ""
        if isinstance(usage, dict):
            total_tokens = usage.get("total_tokens")
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            cached_tokens = usage.get("cached_tokens")
            if isinstance(total_tokens, int):
                usage_text = f" ({total_tokens} tokens)"
            stats_parts: list[str] = []
            if isinstance(prompt_tokens, int):
                stats_parts.append(f"prompt {prompt_tokens}")
            if isinstance(completion_tokens, int):
                stats_parts.append(f"completion {completion_tokens}")
            if isinstance(cached_tokens, int):
                stats_parts.append(f"cached {cached_tokens}")
            if isinstance(total_tokens, int):
                stats_parts.append(f"total {total_tokens}")
            if stats_parts:
                usage_text = f" {SEPARATOR} " + f" {SEPARATOR} ".join(stats_parts)

        summary_text = ""
        if isinstance(summary, str) and summary.strip():
            line_count = len(summary.strip().splitlines())
            summary_text = f"{SEPARATOR} summary {line_count} lines"

        self.console.print(
            Text.assemble(
                (f"  {TOOL_ICON_SUCCESS} ", "success"),
                ("Context compaction complete", "dim white"),
                (usage_text, "muted"),
                (f" {summary_text}" if summary_text else "", "muted"),
            )
        )

        if self._assistant_stream_open:
            verb = _random_verb()
            spinner = Spinner("dots", text=f"[thinking]{verb}...[/]", style="thinking")
            if self._live_display is not None:
                try:
                    self._live_display.update(spinner)
                except Exception:
                    pass
            else:
                self._live_display = Live(
                    spinner,
                    console=self.console,
                    refresh_per_second=12,
                    vertical_overflow="visible",
                    transient=True,
                )
                self._live_display.start()
            self._start_verb_rotation(style="thinking")

    def subagent_started(self, subagent_name: str) -> None:
        """Display when a subagent is invoked"""
        style = f"subagent.{subagent_name}" if f"subagent.{subagent_name}" in AGENT_THEME.styles else "subagent"
        self.console.print(
            Text.assemble(
                (f"  {DIAMOND_FILLED} ", style),
                ("Invoking ", "muted"),
                (subagent_name, style),
                (" subagent", "muted"),
            )
        )

    def info(self, message: str) -> None:
        """Display info message"""
        self.console.print(
            Text.assemble(
                ("  ℹ ", "info"),
                (message, "dim white"),
            )
        )

    def success(self, message: str) -> None:
        """Display success message"""
        self.console.print(
            Text.assemble(
                (f"  {TOOL_ICON_SUCCESS} ", "success"),
                (message, "dim white"),
            )
        )

    def warning(self, message: str) -> None:
        """Display warning message"""
        self.console.print(
            Text.assemble(
                ("  ⚠ ", "warning"),
                (message, "dim white"),
            )
        )

    def show_help(self) -> None:
        help_text = """\
## Commands

| Command | Description |
|---|---|
| `/help` | Show this help |
| `/exit` or `/quit` | Exit the agent |
| `/clear` | Clear conversation history |
| `/config` | Show current configuration |
| `/model <name>` | Change the model |
| `/approval <mode>` | Change approval mode |
| `/stats` | Show session statistics |
| `/tools` | List available tools |
| `/mcp` | Show MCP server status |
| `/save` | Save current session |
| `/checkpoint [name]` | Create a checkpoint |
| `/checkpoints` | List available checkpoints |
| `/restore <id>` | Restore a checkpoint |
| `/sessions` | List saved sessions |
| `/resume <id>` | Resume a saved session |

## Tips

- Just type your message to chat with the agent
- The agent can read, write, and execute code
- Use `@filename` to mention and attach files
- Some operations require approval (can be configured)
"""
        self.console.print(Markdown(help_text))

    # ─── Arg Rendering Helpers ────────────────────────────────────────────

    def _ordered_args(self, tool_name: str, args: dict[str, Any]) -> list[tuple[str, Any]]:
        """Show the most important arguments of a tool call first in the TUI."""
        _PREFERRED_ORDER = {
            'read_file': ['path', 'offset', 'limit', 'show_file'],
            "write_file": ["path", "create_directories", "content"],
            "edit_file": ["path", "replace_all", "old_string", "new_string"],
            "shell": ["command", "timeout", "cwd"],
            "list_dir": ["path", "include_hidden"],
            "grep": ["path", "case_insensitive", "pattern"],
            "glob": ["path", "pattern"],
            "todos": ["id", "action", "content"],
            "memory": ["action", "scope", "key", "value", "ttl_seconds"],
        }

        preferred = _PREFERRED_ORDER.get(tool_name, [])
        ordered: list[tuple[str, Any]] = []
        seen = set()

        for key in preferred:
            if key in args:
                ordered.append((key, args[key]))
                seen.add(key)

        remaining_keys = set(args.keys()) - seen
        ordered.extend([(key, args[key]) for key in remaining_keys])
        return ordered

    def _render_args_table(self, tool_name: str, args: dict[str, Any]) -> Table:
        table = Table.grid(padding=(0, 1))
        table.add_column(style="muted", justify="right", no_wrap=True)
        table.add_column(overflow="fold")

        for key, value in self._ordered_args(tool_name, args):
            if key in {'content', 'old_string', 'new_string', 'text', 'body'} and isinstance(value, str):
                line_count = len(value.splitlines()) or 0
                byte_count = len(value.encode('utf-8'))
                value = f"<{line_count} lines, {byte_count} bytes of text>"

            if isinstance(value, bool):
                value = str(value)

            table.add_row(key, self._format_arg_value(key, value))
        return table

    def _format_arg_value(self, key: str, value: Any) -> Text:
        """Render a single argument value with type-aware styling."""
        if isinstance(value, bool):
            return Text(str(value), style="#22d3ee" if value else "muted")
        if isinstance(value, (int, float)):
            return Text(str(value), style="bold bright_white")
        if not isinstance(value, str):
            value = str(value)

        # Decide max length
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

    def _extract_read_file_content(self, text: str) -> tuple[int, str] | None:
        """Extract file content from read_file tool output."""
        body = text
        header = re.match(r"^Showing lines (\d+) to (\d+) of (\d+)\n\n", text)

        if header:
            body = text[header.end():]

        code_lines: list[str] = []
        start_line: int = 0

        for line in body.splitlines():
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
