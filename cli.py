import re
from agent.agent import Agent
from agent.events import AgentEventType
from config.config import Config
from ui.tui import TUI, get_console
from rich.panel import Panel
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
    "prompt":           "#00ffff bold",
    # Autocomplete dropdown
    "completion-menu.completion":            "bg:#1e1e2e #cdd6f4",
    "completion-menu.completion.current":    "bg:#89b4fa #1e1e2e bold",
    "completion-menu.meta.completion":       "bg:#1e1e2e #6c7086",
    "completion-menu.meta.completion.current": "bg:#89b4fa #1e1e2e",
    "scrollbar.background":                  "bg:#313244",
    "scrollbar.button":                      "bg:#89b4fa",
    # Bottom toolbar
    "bottom-toolbar":                        "bg:#1e1e2e #6c7086",
    "bottom-toolbar.text":                   "#89dceb",
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
        session: PromptSession = PromptSession(
            history=InMemoryHistory(),
            completer=command_completer,
            complete_while_typing=True,
            style=PROMPT_STYLE,
            bottom_toolbar=HTML('<b><style bg="#1e1e2e" fg="#89dceb"> / </style></b> for commands  <b>↑↓</b> history  <b>ctrl+c</b> exit'),
        )

        async with Agent(self.config) as agent:
            self.agent = agent 
            while True:
                try:
                    user_input = await session.prompt_async(">>> ")
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

