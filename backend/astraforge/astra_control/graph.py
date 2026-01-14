import json
import operator
import logging
from typing import Annotated, List, Optional, TypedDict, Union
from pydantic import BaseModel, Field

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from .state import AgentState
from .tools import get_tools

logger = logging.getLogger(__name__)

def create_graph(
    model_name: str, 
    api_key: str, 
    base_url: str, 
    sandbox_session_id: str, 
    provider: str = "openai", 
    proxy_url: str = None,
    reasoning_check: bool = False,
    reasoning_effort: str = "high"
):
    # ... (llm initialization same as before)
    if provider == "openai":
        if proxy_url:
            llm = ChatOpenAI(model=model_name, api_key=api_key or "proxy", base_url=f"{proxy_url.rstrip('/')}/providers/openai/v1")
        else:
            llm = ChatOpenAI(model=model_name, api_key=api_key)
    elif provider == "anthropic":
        if proxy_url:
            llm = ChatOpenAI(model=model_name, api_key=api_key or "proxy", base_url=f"{proxy_url.rstrip('/')}/providers/anthropic/v1")
        else:
            llm = ChatAnthropic(model=model_name, api_key=api_key)
    elif provider == "ollama":
        if proxy_url:
            kwargs = {}
            if reasoning_check:
                kwargs["model_kwargs"] = {"think": reasoning_effort}
            llm = ChatOpenAI(
                model=model_name, 
                api_key=api_key or "proxy", 
                base_url=f"{proxy_url.rstrip('/')}/providers/ollama/v1",
                **kwargs
            )
        else:
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            llm = ChatOllama(
                model=model_name,
                base_url=ollama_url
            )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    tools = get_tools(sandbox_session_id)
    llm_with_tools = llm.bind_tools(tools)

    class PlanStep(BaseModel):
        title: str = Field(description="Short title of the step")
        description: str = Field(description="Detailed description of what to do")
        status: str = Field(description="Current status: todo, in_progress, completed")

    class Plan(BaseModel):
        steps: List[PlanStep] = Field(description="The list of steps to achieve the goal")
        markdown_plan: str = Field(description="The plan in todo.md format")

    def planner(state: AgentState):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a master planner for an AI agent. Given the goal, create a step-by-step plan. Keep track of progress."),
            MessagesPlaceholder(variable_name="messages"),
            ("system", "Current Plan: {plan}\nSummary of progress: {summary}")
        ])
        
        # If the provider doesn't support structured output well, we might need a fallback.
        # But ChatOpenAI (and Ollama via proxy) usually support it.
        try:
            planner_llm = llm.with_structured_output(Plan)
            chain = prompt | planner_llm
            response = chain.invoke({
                "messages": state["messages"],
                "plan": state.get("plan", "No plan yet."),
                "summary": state.get("summary", "Starting...")
            })
            return {
                "plan": response.markdown_plan,
                "plan_steps": [step.dict() for step in response.steps]
            }
        except Exception as e:
            logger.error(f"Error in structured planner: {e}")
            # Fallback to simple markdown if structured output fails
            chain = prompt | llm
            response = chain.invoke({
                "messages": state["messages"],
                "plan": state.get("plan", "No plan yet."),
                "summary": state.get("summary", "Starting...")
            })
            return {"plan": response.content}

    def agent(state: AgentState):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an AI agent controlling a Ubuntu environment. Your primary workspace is /workspace. You should create files and perform operations within this directory unless explicitly told otherwise. Goal: {goal}\nPlan:\n{plan}\n\nYou must only call ONE tool at a time. After each tool call, you will receive an observation. If you need to speak to the user or if you are stuck, just provide your message without a tool call and the user will be prompted to help you."),
            MessagesPlaceholder(variable_name="messages"),
        ])
        chain = prompt | llm_with_tools
        response = chain.invoke({
            "goal": state["messages"][0].content,
            "plan": state.get("plan", ""),
            "messages": state["messages"]
        })
        return {"messages": [response]}

    def should_continue(state: AgentState):
        messages = state["messages"]
        if not messages:
            return "agent"
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        if isinstance(last_message, AIMessage) and "FINAL ANSWER" in (last_message.content or ""):
            return END
        # If no tool calls and no final answer, or if it's not an AIMessage (e.g. HumanMessage from resume),
        # we wait for user or go to agent.
        if isinstance(last_message, HumanMessage):
            return "agent"
        return "wait_for_user"

    def check_takeover(state: AgentState):
        for message in reversed(state["messages"]):
            if isinstance(message, ToolMessage) and "TAKEOVER_REQUESTED" in message.content:
                return "wait_for_user"
        return "observer"

    def wait_for_user(state: AgentState):
        return {"waiting_for_user": True}

    def observer(state: AgentState):
        # Capture last terminal output
        last_terminal = None
        for message in reversed(state["messages"]):
            if isinstance(message, ToolMessage):
                last_terminal = message.content
                break
        
        # Try to find list_files tool to refresh file tree
        file_tree = state.get("file_tree", [])
        for t in tools:
            # We check the __name__ or name attribute of the tool
            if getattr(t, "name", "") == "list_files":
                try:
                    file_tree = t.invoke({"path": "."}).split("\n")
                except:
                    pass
        
        return {
            "terminal_output": last_terminal,
            "file_tree": file_tree
        }

    def summarizer(state: AgentState):
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an observer for an AI agent. Summarize the progress made so far based on the conversation history. Be concise. Current summary: {summary}"),
            MessagesPlaceholder(variable_name="messages"),
        ])
        chain = prompt | llm
        response = chain.invoke({
            "messages": state["messages"],
            "summary": state.get("summary", "")
        })
        return {"summary": response.content}

    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner)
    workflow.add_node("agent", agent)
    workflow.add_node("tools", ToolNode(tools))
    workflow.add_node("wait_for_user", wait_for_user)
    workflow.add_node("observer", observer)
    workflow.add_node("summarizer", summarizer)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "wait_for_user": "wait_for_user",
            END: END
        }
    )
    workflow.add_conditional_edges(
        "tools",
        check_takeover,
        {
            "wait_for_user": "wait_for_user",
            "observer": "observer"
        }
    )
    workflow.add_edge("observer", "summarizer")
    workflow.add_edge("wait_for_user", "summarizer")
    workflow.add_edge("summarizer", "planner")

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["tools", "wait_for_user"])

