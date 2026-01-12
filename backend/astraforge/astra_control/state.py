from typing import Annotated, List, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # The messages in the conversation
    messages: Annotated[List[BaseMessage], add_messages]
    # Current plan of the agent (markdown)
    plan: Optional[str]
    # Structured plan steps
    plan_steps: List[dict]
    # Current step in the plan
    current_step: int
    # Summary of the progress
    summary: str
    # Environment info
    env_info: dict
    # Current screenshot (b64)
    screenshot: Optional[str]
    # Last terminal output
    terminal_output: Optional[str]
    # File tree
    file_tree: List[str]
    # Is the agent waiting for user?
    waiting_for_user: bool
    # Is the agent finished?
    is_finished: bool
