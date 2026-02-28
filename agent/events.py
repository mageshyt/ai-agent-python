from __future__ import annotations
from enum import Enum
from dataclasses import dataclass , field
from typing import Any

from lib.response import TokenUsage


class AgentEventType(str,Enum):
    # Agent lifecycle events
    AGENT_STARTED = "agent_started"
    AGENT_FINISHED = "agent_finished"
    AGENT_ERROR = "agent_error"

    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"

    # Tool events
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_ERROR = "tool_error"


@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict[str,Any] = field(default_factory=dict)
    
    @classmethod
    def agent_started(cls, agent_name: str, message:str) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_STARTED,
            data={"agent_name": agent_name , 'message':message }
                  )

    @classmethod
    def agent_finished(cls, 
                       agent_name: str,
                       response:str | None = None,
                       usage:TokenUsage | None = None
            ) -> AgentEvent:
        
        return cls(
            type=AgentEventType.AGENT_FINISHED,
            data={"agent_name": agent_name , 
                  'response':response , 
                  'usage': usage.__dict__ if usage else None}
            )

    @classmethod
    def agent_error(cls, agent_name: str, message:str , details:dict[str,Any] | None = None) -> AgentEvent:
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={"agent_name": agent_name , 'message':message , 'details': details or {}}
        )


    @classmethod
    def text_delta(cls, agent_name: str, content:str) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_DELTA,
            data={"agent_name": agent_name , 'content':content }
        )


    @classmethod
    def text_complete(cls, agent_name: str, content:str) -> AgentEvent:
        return cls(
            type=AgentEventType.TEXT_COMPLETE,
            data={"agent_name": agent_name ,
                  'content':content 
                  }
            )

