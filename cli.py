from agent.agent import Agent
from agent.events import AgentEventType
from ui.tui import TUI, get_console

console = get_console()


class CLI:
    def __init__(self):
        self.agent : Agent | None = None
        self.tui = TUI(console)

    async def  run_single(self,message:str):

        async with Agent() as agent:
            self.agent = agent
            return await self._process_message(message)

    async def _process_message(self, message:str) -> str | None:
        if not self.agent:
            self.tui.agent_error("Agent is not initialized.")
            return None

        self.tui.begin_assistant()
        final_response = None
        
        async for event in self.agent.run(message):
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
                    
                case AgentEventType.AGENT_FINISHED:
                    agent_name = event.data.get('agent_name', 'unknown')
                    response = event.data.get('response')
                    self.tui.agent_finished(agent_name, response)
                    
                case AgentEventType.AGENT_ERROR:
                    error_msg = event.data.get('message', 'Unknown error')
                    self.tui.agent_error(error_msg)
        
        self.tui.end_assistant()
        return final_response

    async def run_interactive(self):
        self.tui.show_welcome_message()

        async with Agent() as agent:
            self.agent = agent 
            while True:
                user_input = console.input("[bold blue]You:[/] ")
                if user_input.strip().lower() == "exit":
                    console.print("[bold red]Exiting... Goodbye![/]")
                    break
                if user_input.strip() == '/help':
                    self.tui.show_help()
                
                await self._process_message(user_input)