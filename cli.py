import re
import subprocess
from pathlib import Path
from agent.agent import Agent
from agent.events import AgentEventType
from config.config import Config
from ui.tui import TUI, get_console
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML


console = get_console()

COMMANDS = [
    "/help", "/exit", "/quit", "/clear",
    "/config", "/model", "/stats", "/tools",
    "/save", "/sessions",
]

PROMPT_STYLE = Style.from_dict({
    # Input prompt
    "prompt":                              "#00ffff bold",
    "prompt.chrome":                       "#7aa2f7 bold",
    "prompt.brand":                        "#7dcfff bold",
    "prompt.arrow":                        "#bb9af7 bold",
    "prompt.input":                        "#c0caf5",
    "rprompt":                             "#7aa2f7",
    # Autocomplete dropdown
    "completion-menu.completion":            "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current":    "bg:#89b4fa #1e1e2e bold",
    "completion-menu.meta.completion":       "bg:#1e1e2e #6c7086",
    "completion-menu.meta.completion.current": "bg:#89b4fa #1e1e2e",
    "scrollbar.background":                  "bg:#313244",
    "scrollbar.button":                      "bg:#89b4fa",
    # Bottom toolbar
    "bottom-toolbar":                        "#000000 nounderline",
    "bottom-toolbar.text":                   "#9aa5ce",
    "bottom-toolbar.key":                    "#8bd5ff bold",
    "bottom-toolbar.path":                   "#c6d0f5",
    "bottom-toolbar.branch":                 "#8aadf4",
})

command_completer = WordCompleter(COMMANDS, pattern=re.compile(r"\/\w*"), sentence=True)


class CLI:
    def __init__(self,config:Config):
        self.agent : Agent | None = None
        self.config = config
        self.tui = TUI(console,config)

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
        
        self.tui.end_assistant()
        return final_response

    async def run_interactive(self):
        self.tui.show_welcome_message()
        cwd_name = Path(self.config.cwd).name
        branch = self._get_git_branch(self.config.cwd)
        branch_text = f"[{branch}]" if branch else ""
        session: PromptSession = PromptSession(
            history=InMemoryHistory(),
            completer=command_completer,
            complete_while_typing=True,
            style=PROMPT_STYLE,
            bottom_toolbar=HTML(self._build_bottom_toolbar(cwd_name, branch_text)),
        )

        async with Agent(self.config) as agent:
            self.agent = agent 
            while True:
                try:
                    user_input = await session.prompt_async(
                        HTML(
                            '<style fg="#c0caf5">></style> '
                        ),
                        placeholder=HTML(
                            '<style fg="#6c7086">Enter @ to mention files or / for commands</style>'
                        ),
                        rprompt=HTML(
                            f'<style fg="#7aa2f7">{self.config.get_model_name}</style>'
                        ),
                    )
                except (EOFError, KeyboardInterrupt):
                    console.print("[bold red]Exiting... Goodbye![/]")
                    break

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
                else:
                    await self._process_message(cmd)

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
            '<style fg="#8bd5ff">Ctrl+C</style><style fg="#9aa5ce"> Exit</style>'
            '<style fg="#8bd5ff">  ·  </style>'
            '<style fg="#8bd5ff">/</style><style fg="#9aa5ce"> Commands</style>'
            '<style fg="#8bd5ff">  ·  </style>'
            '<style fg="#8bd5ff">@</style><style fg="#9aa5ce"> Mention files</style>'
            f'<style fg="#8bd5ff">{padding}</style>'
            f'<style fg="#c6d0f5">~/{cwd_name}</style>'
            f'<style fg="#8aadf4"> {branch_text}</style>'
        )