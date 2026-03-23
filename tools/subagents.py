import asyncio
from dataclasses import dataclass
from pydantic import BaseModel, Field

from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult

class SubAgentParams(BaseModel):
    goal : str = Field(
            ... ,
            description = (
                "The goal that the sub-agent should achieve. "
                "The sub-agent will be given this goal and will use its own tools to achieve it. The sub-agent will return the result of its actions to the main agent. "
                "The sub-agent will have a limited number of turns and a timeout to achieve its goal. "
                "The sub-agent can only use the tools that are allowed for it."
                )
            )


@dataclass
class SubAgentDefinition:
    name : str
    description : str
    goal_prompt : str
    allowed_tools : list[str] | None = None
    max_turns : int = 15
    timeout_seconds : float = 200


class SubAgentTool(Tool):
    kind = ToolKind.MCP

    def __init__(self,config:Config, definition : SubAgentDefinition):
        super().__init__(config)
        self.definition = definition

    schema = SubAgentParams
    @property
    def name(self) -> str:
        return f"subagent_{self.definition.name}"

    @property
    def description(self) -> str:
        return f"subagent_{self.definition.name} is a sub-agent that can be called by the main agent to achieve a specific goal. The sub-agent will be given a goal and will use its own tools to achieve that goal. The sub-agent will return the result of its actions to the main agent. The sub-agent will have a limited number of turns and a timeout to achieve its goal. The sub-agent can only use the tools that are allowed for it."

    def is_mutating(self) -> bool:
        return True

    async def execute(self, invocation: ToolInvocation)->ToolResult:
        from agent.events import AgentEventType
        from agent.agent import Agent

        params = SubAgentParams(**invocation.params)
        goal = params.goal

        if not goal:
            return ToolResult.error_result("Goal is required")
        final_response:str | None = None
        tool_calls = []
        error = None
        terminate_response = None

        try:
            config_dict = self.config.to_dict()

            config_dict["max_turns"] = self.definition.max_turns
            config_dict["allowed_tools"] = self.definition.allowed_tools
            config_dict["user_instructions"] = self._render_goal_prompt(goal)

            sub_agent_config = Config(**config_dict)

            final_prompt = self._get_final_prompt(goal)

            async with Agent(config=sub_agent_config) as sub_agent:
                try:
                    async with asyncio.timeout(self.definition.timeout_seconds):
                        async for event in sub_agent.run(final_prompt):
                            match event.type:
                                case AgentEventType.TOOL_STARTED:
                                    tool_name = event.data.get("tool_name") if event.data.get("tool_name") else "Unknown tool"
                                    tool_calls.append(tool_name)
                                case AgentEventType.AGENT_FINISHED:
                                    if final_response is None:
                                        final_response = event.data.get("response") if event.data.get("response") else "No response"
                                case AgentEventType.TEXT_COMPLETE:
                                    final_response = event.data.get("content") if event.data.get("content") else None
                                case AgentEventType.AGENT_ERROR:
                                    error = event.data.get("message") if event.data.get("message") else "Unknown error"
                                    break
                except TimeoutError:
                    terminate_response = f"Sub-agent '{self.definition.name}' timed out after {self.definition.timeout_seconds} seconds."
                    final_response = terminate_response

        except Exception as e:
            terminate_response = f"Sub-agent '{self.definition.name}' encountered an error: {str(e)}"
            error = str(e)
            final_response = terminate_response

        if not error and terminate_response is None:
            terminate_response = "completed"

        result = self._get_final_result(tool_calls, final_response,  terminate_response)

        if error:
            return ToolResult.error_result(error, metadata={"tool_calls": tool_calls, "final_response": final_response})
        else:
            return ToolResult.success_result(result, metadata={"tool_calls": tool_calls, "final_response": final_response})


    def _get_final_prompt(self, goal:str) -> str:
        rendered_goal_prompt = self._render_goal_prompt(goal)

        prompt = f"""You are a specialized sub-agent with a specific task to complete.

            {rendered_goal_prompt}

            YOUR TASK:
            {goal}

            IMPORTANT:
            - Focus only on completing the specified task
            - Do not engage in unrelated actions
            - Once you have completed the task or have the answer, provide your final response
            - Be concise and direct in your output
            """


        return prompt

    def _render_goal_prompt(self, goal: str) -> str:
        try:
            return self.definition.goal_prompt.format(goal=goal)
        except Exception:
            return f"{self.definition.goal_prompt}\n\nYOUR TASK:\n{goal}"


    def _get_final_result(self, tool_calls:list[str], final_response:str | None, terminate_response:str | None) -> str:
        result = f"""Sub-agent '{self.definition.name}' completed. 
        Termination: {terminate_response}
        Tools called: {', '.join(tool_calls) if tool_calls else 'None'}

        Result:
        {final_response or 'No response'}
        """

        return result

