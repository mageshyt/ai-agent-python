import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import Callable
from agent.agent import Agent
from config.config import Config
from agent.events import AgentEventType
from ui.tui import TUI, get_console
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import  Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.formatted_text import HTML
from lib import IGNORED_DIRECTORIES


console = get_console()

COMMANDS = [
    "/help", "/exit", "/quit", "/clear",
    "/config", "/model", "/stats", "/tools",
    "/save", "/sessions", "/mcp"
]

class SystemCommandCompleter(Completer):
    def __init__(self, commands):
        self.commands = commands
        
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        match = re.search(r'(?<!\S)(/[A-Za-z0-9_-]*)$', text)
        if not match:
            return
            
        typed = match.group(1).lower()
        for cmd in self.commands:
            if cmd.startswith(typed):
                yield Completion(
                    cmd,
                    start_position=-len(typed),
                    display=f"⚡ {cmd}"
                )

class FileMentionCompleter(Completer):
    def __init__(
        self,
        cache: list[str] | None = None,
        cache_provider: Callable[[], list[str]] | None = None,
        refresh_interval: float = 2.0,
    ):
        self.cache = cache or []
        self.cache_provider = cache_provider
        self.refresh_interval = refresh_interval
        self._last_refresh = 0.0

    def _get_cache(self) -> list[str]:
        if not self.cache_provider:
            return self.cache

        now = time.monotonic()
        if now - self._last_refresh >= self.refresh_interval:
            try:
                self.cache = self.cache_provider()
            except Exception:
                pass
            self._last_refresh = now

        return self.cache

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        # Look for @ followed by any path characters at the very end of typed string
        match = re.search(r'@([A-Za-z0-9_\-\.\/]*)$', text)
        if not match:
            return

        typed = match.group(1)
        typed_lower = typed.lower()
        cache = self._get_cache()
        
        # Fuzzy/Substring match against the cached files
        matches = [f for f in cache if typed_lower in f.lower()]
        
        # Sort so that exact prefix matches appear first
        matches.sort(key=lambda x: (not x.lower().startswith(typed_lower), x))

        # Show max 15 to keep UI clean
        for match_file in matches[:15]:
            yield Completion(
                match_file,
                start_position=-len(typed),
                display=f"{match_file}"
            )

class UnifiedCompleter(Completer):
    def __init__(self, cmd_completer: Completer, fs_completer: Completer):
        self.cmd_completer = cmd_completer
        self.fs_completer = fs_completer

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if re.search(r'@[A-Za-z0-9_\-\.\/]*$', text):
            yield from self.fs_completer.get_completions(document, complete_event)
        elif re.search(r'(?<!\S)/[A-Za-z0-9_-]*$', text):
            yield from self.cmd_completer.get_completions(document, complete_event)

PROMPT_STYLE = Style.from_dict({
    # Input prompt — cyan/teal palette
    "prompt":                              "#22d3ee bold",
    "prompt.chrome":                       "#0891b2 bold",
    "prompt.brand":                        "#67e8f9 bold",
    "prompt.arrow":                        "#22d3ee bold",
    "prompt.input":                        "#cffafe",
    "rprompt":                             "#67e8f9",
    # Autocomplete dropdown — dark cyan-tinted
    "completion-menu":                       "bg:#0a1a1f #a5f3fc",
    "completion-menu.completion":            "bg:#0a1a1f #a5f3fc",
    "completion-menu.completion.current":    "bg:#155e75 #ffffff bold",
    "completion-menu.meta.completion":       "bg:#0a1a1f #155e75",
    "completion-menu.meta.completion.current": "bg:#155e75 #cffafe",
    "scrollbar.background":                  "bg:#0a1219",
    "scrollbar.button":                      "bg:#155e75",
    # Bottom toolbar — cyan tones
    "bottom-toolbar":                        "#000000 nounderline",
    "bottom-toolbar.text":                   "#67e8f9",
    "bottom-toolbar.key":                    "#22d3ee bold",
    "bottom-toolbar.path":                   "#cffafe",
    "bottom-toolbar.branch":                 "#67e8f9",
})

command_completer = SystemCommandCompleter(COMMANDS)




class CLI:
    def __init__(self,config:Config):
        self.agent : Agent | None = None
        self.config:Config = config
        self.tui = TUI(console,config)
        self.filesystem_completer = self._get_filesystem_completer(Path(config.cwd))


    async def  run_single(self,message:str) -> str | None:
        """ Run a single message through the agent and return the final response.

        Args:
            message (str): user message prompt

        Returns:
            str | None: final response from the agent, or None if there was an error
        """

        async with Agent(self.config) as agent:
            self.agent = agent
            return await self._process_message(message)

    async def _process_message(self, message:str) -> str | None:
        """ Process a user message by sending it to the agent and handling the response events.

        Args:
            message (str): user message prompt

        Returns:
            str | None: final response from the agent, or None if there was an error
        """
        if not self.agent:
            self.tui.agent_error("Agent is not initialized.")
            return None

        # Parse file mentions and attach context explicitly 
        file_mentions = list(set(re.findall(r'@([^\s]+)', message)))
        context_blocks = []
        
        for file_path in file_mentions:
            full_path = Path(self.config.cwd) / file_path
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8")
                    context_blocks.append(f"--- File: {file_path} ---\n{content}\n")
                    self.tui.agent_started("System", f"Attached file: {file_path}")
                except Exception as e:
                    self.tui.agent_error(f"Could not read {file_path}: {e}")
            else:
                self.tui.agent_error(f"File not found: {file_path}")
                
        if context_blocks:
            message = message + "\n\nAttached Context:\n" + "\n".join(context_blocks)

        self.tui.begin_assistant()
        final_response = None
        
        async for event in self.agent.run(message):
            # print("Received event:", event.type, event.data)  # Debugging log
            match event.type:
                case AgentEventType.AGENT_STARTED:
                    agent_name = event.data.get('agent_name', 'unknown')
                    msg = event.data.get('message', '')
                    self.tui.agent_started(agent_name, msg)
                    self.tui.assistant_thinking("Thinking")
                    
                case AgentEventType.TEXT_DELTA:
                    content = event.data.get("content", "")
                    self.tui.stream_assistant_delta(content)
                    
                case AgentEventType.TEXT_COMPLETE:
                    content = event.data.get("content", "No content")
                    final_response = content
                    self.tui.text_complete(content)

                case AgentEventType.TOOL_STARTED:
                    tool_name = event.data.get('tool_name', 'unknown')
                    tool_kind = self._get_tool_kind(tool_name)
                    self.tui.tool_call_started(
                        call_id=event.data.get('call_id', ''),
                        tool_name=tool_name,
                        arguments=event.data.get('arguments', {}),
                        tool_kind=tool_kind
                    )
                case AgentEventType.TOOL_FINISHED:
                    tool_kind = self._get_tool_kind(event.data.get('tool_name', 'unknown'))
                    self.tui.tool_call_finished(
                            call_id=event.data.get('call_id', ''),
                            tool_name=event.data.get('tool_name', 'unknown'),
                            success=event.data.get('success', False),
                            tool_kind=tool_kind,
                            output=event.data.get('output', ''),
                            error=event.data.get('error', ''),
                            truncated=event.data.get('truncated', False),
                            metadata=event.data.get('metadata', None),
                            diff=event.data.get('diff'),
                            exit_code=event.data.get('exit_code', None)
                    )
                    
                case AgentEventType.AGENT_FINISHED:
                    agent_name = event.data.get('agent_name', 'unknown')
                    response = event.data.get('response')
                    usage = event.data.get('usage')
                    self.tui.agent_finished( agent_name, response )
                    
                case AgentEventType.AGENT_ERROR:
                    error_msg = event.data.get('message', 'Unknown error')
                    self.tui.agent_error(error_msg)

                case AgentEventType.COMPACTION_STARTED:
                    self.tui.compaction_started()

                case AgentEventType.COMPACTION_FINISHED:
                    summary = event.data.get('summary', '')
                    usage = event.data.get('usage')
                    self.tui.compaction_finished( summary, usage)    

                case AgentEventType.COMPACTION_FAILED:
                    reason = event.data.get('reason', 'Unknown reason')
                    self.tui.warning(f"Context compaction failed: {reason}")


        self.tui.end_assistant()
        return final_response

    async def run_interactive(self):
        self.tui.show_welcome_message()
        cwd_name = Path(self.config.cwd).name
        branch = self._get_git_branch(self.config.cwd)
        branch_text = f"[{branch}]" if branch else ""
        session: PromptSession = PromptSession(
            history=InMemoryHistory(),
            completer=UnifiedCompleter(command_completer, self.filesystem_completer),
            complete_while_typing=True,
            complete_style=CompleteStyle.COLUMN,
            style=PROMPT_STYLE,
            # bottom_toolbar=HTML(self._build_bottom_toolbar(cwd_name, branch_text)),
        )

        import time as _time
        _last_interrupt = 0.0

        async with Agent(self.config) as agent:
            self.agent = agent 
            while True:
                try:
                    user_input = await session.prompt_async(
                        HTML(
                            '<style fg="#22d3ee">❯</style> '
                        ),
                        placeholder=HTML(
                            '<style fg="#6c7086">Enter @ to mention files or / for commands</style>'
                        ),
                        rprompt=HTML(
                            f'<style fg="#67e8f9">{self.config.get_model_name}</style>'
                        ),
                    )
                    _last_interrupt = 0.0  # reset on successful input
                except (EOFError, KeyboardInterrupt):
                    now = _time.monotonic()
                    if now - _last_interrupt < 2.0:
                        # Second Ctrl+C within 2s — exit
                        console.print("\n[bold #22d3ee]Goodbye![/]")
                        break
                    else:
                        _last_interrupt = now
                        console.print("\n[dim]Press Ctrl+C again to exit[/dim]")
                        continue

                cmd = user_input.strip()
                if not cmd:
                    continue
                elif cmd.lower() in ("exit", "/exit", "/quit"):
                    console.print("[bold red]Exiting... Goodbye![/]")
                    break
                elif cmd == "/help":
                    self.tui.show_help()
                elif cmd == "/clear":
                    console.clear()
                elif cmd == "/mcp":
                    mcp_servers = self.agent.session.mcp_manager.get_all_servers()
                    if mcp_servers:
                        self.tui.show_mcp_servers(mcp_servers)
                    else:
                        self.tui.warning("No MCP servers registered.")

                else:
                    task = asyncio.create_task(self._process_message(cmd))
                    try:
                        await task
                    except KeyboardInterrupt:
                        # Ctrl+C during agent work — cancel the task properly
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, KeyboardInterrupt):
                            pass
                        self.tui.end_assistant()
                        console.print("\n[dim]⏹ Interrupted[/dim]")
                    except asyncio.CancelledError:
                        self.tui.end_assistant()
                        console.print("\n[dim]⏹ Cancelled[/dim]")

    def _get_tool_kind(self, tool_name:str) -> str:
        if not self.agent:
            return "unknown"
        tool_detail = self.agent.session.tool_registry.get_tool(tool_name)
        return tool_detail.kind if tool_detail else "unknown"

    def _get_git_branch(self, cwd: Path) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            branch = result.stdout.strip()
            if result.returncode == 0 and branch and branch != "HEAD":
                return branch
            return None
        except Exception:
            return None

    def _build_bottom_toolbar(self, cwd_name: str, branch_text: str) -> str:
        import shutil
        terminal_width = shutil.get_terminal_size().columns
        
        # Raw text lengths for width calculation
        left_text = "Ctrl+C Exit  ·  / Commands  ·  @ Mention files"
        right_text = f"~/{cwd_name} {branch_text}".strip()
        
        # Calculate padding to push the right_text to the edge
        padding_len = max(1, terminal_width - len(left_text) - len(right_text) - 1)
        padding = " " * padding_len
        
        return (
            '<style fg="#22d3ee">Ctrl+C</style><style fg="#67e8f9"> Exit</style>'
            '<style fg="#155e75">  ·  </style>'
            '<style fg="#22d3ee">/</style><style fg="#67e8f9"> Commands</style>'
            '<style fg="#155e75">  ·  </style>'
            '<style fg="#22d3ee">@</style><style fg="#67e8f9"> Mention files</style>'
            f'<style fg="#155e75">{padding}</style>'
            f'<style fg="#cffafe">~/{cwd_name}</style>'
            f'<style fg="#67e8f9"> {branch_text}</style>'
        )
    
    def _get_filesystem_completer(self, cwd: Path) -> Completer:
        initial_cache = self._build_filesystem_cache(cwd)
        return FileMentionCompleter(
            cache=initial_cache,
            cache_provider=lambda: self._build_filesystem_cache(cwd),
            refresh_interval=2.0,
        )

    def _build_filesystem_cache(self, cwd: Path) -> list[str]:
        import os

        file_list: list[str] = []
        for root, dirs, files in os.walk(cwd):
            if any(ignored in root.split(os.sep) for ignored in IGNORED_DIRECTORIES):
                continue
            for name in files:
                if any(ignored in name for ignored in IGNORED_DIRECTORIES):
                    continue
                rel_path = os.path.relpath(os.path.join(root, name), cwd)
                # Normalize slashes for consistency
                if os.name == 'nt':
                    rel_path = rel_path.replace('\\', '/')
                file_list.append(rel_path)
        return file_list
