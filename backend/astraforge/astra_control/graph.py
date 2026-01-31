import logging
import os
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ValidationError

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from .state import AgentState
from .tools import SandboxToolset, tavily_web_search

logger = logging.getLogger(__name__)

def _is_reasoning_model(model: str) -> bool:
    """Check if the model is a reasoning model (o1, o3, etc.)"""
    patterns = ["o1-", "o3-", "o1", "o3"]
    return any(model.lower().startswith(p) for p in patterns)


def _should_disable_ssl_verify() -> bool:
    """Check if SSL verification should be disabled (corporate proxy environments)."""
    return os.getenv("DISABLE_SSL_VERIFY", "0").lower() in {"1", "true", "yes"}

def _create_http_client():
    """Create an HTTP client with custom SSL certificates or verification disabled."""
    import httpx
    import os
    
    # Check if we should disable SSL verification entirely
    if _should_disable_ssl_verify():
        return httpx.Client(verify=False)
    
    # Use custom CA bundle if available (corporate environment)
    ca_bundle = os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
    if ca_bundle and os.path.exists(ca_bundle):
        return httpx.Client(verify=ca_bundle)
    
    return None

def create_graph(
    model_name: str, 
    api_key: str, 
    base_url: str, 
    sandbox_session_id: str, 
    provider: str = "openai", 
    proxy_url: str = None,
    reasoning_check: bool = False,
    reasoning_effort: str = "high",
    validation_required: bool = True,
    checkpointer: Optional[Any] = None
):
    # Create HTTP client with SSL settings
    http_client = _create_http_client()
    
    # ... (llm initialization same as before)
    if provider == "openai":
        if proxy_url:
            llm = ChatOpenAI(model=model_name, api_key=api_key or "proxy", base_url=f"{proxy_url.rstrip('/')}/providers/openai/v1", http_client=http_client)
        else:
            llm = ChatOpenAI(model=model_name, api_key=api_key)
    elif provider == "anthropic":
        if proxy_url:
            llm = ChatOpenAI(model=model_name, api_key=api_key or "proxy", base_url=f"{proxy_url.rstrip('/')}/providers/anthropic/v1", http_client=http_client)
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
                http_client=http_client,
                **kwargs
            )
        else:
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            llm = ChatOllama(
                model=model_name,
                base_url=ollama_url
            )
    elif provider == "google":
        google_api_key = api_key if api_key != "proxy" else (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))

        # Use thinking_level for Gemini 3+ models and recommended temperature
        kwargs = {}
        if "gemini-3" in model_name.lower() or reasoning_check:
            kwargs["thinking_level"] = reasoning_effort # minimal, low, medium, high
            kwargs["temperature"] = 1.0
        else:
            kwargs["temperature"] = 0.3

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=google_api_key,
            **kwargs
        )
    elif provider == "azure_openai":
        # Azure OpenAI always connects directly (no proxy support in llm-proxy)
        from langchain_openai import AzureChatOpenAI
        azure_api_key = api_key if api_key != "proxy" else os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

        kwargs = {}
        # Only add reasoning_effort for o1/o3 reasoning models
        if (reasoning_check or reasoning_effort) and _is_reasoning_model(model_name):
            kwargs["model_kwargs"] = {"reasoning_effort": reasoning_effort}

        llm = AzureChatOpenAI(
            azure_deployment=model_name,
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            temperature=0.3,
            http_client=http_client,
            **kwargs
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    ts = SandboxToolset(sandbox_session_id, validation_required=validation_required)
    tools = [
        tool(ts.run_shell),
        tool(ts.read_file),
        tool(ts.write_file),
        tool(ts.list_files),
        tool(ts.ask_user),
        tool(ts.browser_open_url),
        tool(ts.browser_click),
        tool(ts.browser_type),
        tool(ts.request_user_takeover),
        tavily_web_search
    ]
    llm_with_tools = llm.bind_tools(tools)

    class PlanStep(BaseModel):
        title: str = Field(description="Short title of the step")
        description: str = Field(description="Detailed description of what to do")
        status: str = Field(description="Current status: todo, in_progress, completed")

    class Plan(BaseModel):
        steps: List[PlanStep] = Field(description="The list of steps to achieve the goal")
        markdown_plan: str = Field(description="The plan in todo.md format")

    def planner(state: AgentState):
        # Build uploaded documents section if any
        uploaded_docs_section = ""
        if state.get("uploaded_documents"):
            uploaded_docs_section = "\n\nAVAILABLE UPLOADED DOCUMENTS:\nThe user has already provided the following files in the sandbox:\n"
            for doc in state["uploaded_documents"]:
                uploaded_docs_section += f"- {doc['sandbox_path']}"
                if doc.get('description'):
                    uploaded_docs_section += f" ({doc['description']})"
                uploaded_docs_section += "\n"
            uploaded_docs_section += "These files are ready to use. Do not include steps to upload or locate these files."

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are a master planner for an AI agent. Given the goal, create a step-by-step plan.\n\n"
                "ADAPTIVE PLANNING RULES:\n"
                "1. Sizing: Match the plan depth to the task complexity. Simple tasks (e.g., 'check disk space', 'read one file') should have only 1-2 steps. "
                "Complex projects (e.g., 'build an app', 'debug a system') should have a detailed roadmap.\n"
                "2. Context: Consider the current reasoning level: {reasoning_effort}.\n"
                "3. Progress: Update the status of each step (todo, in_progress, completed) based on the history.\n"
                "4. Keep it focused: Do not add unnecessary steps for trivial operations."
                "{uploaded_documents_info}"
            )),
            MessagesPlaceholder(variable_name="messages"),
            ("system", "Current Plan: {plan}\nSummary of progress: {summary}")
        ])

        # If the provider doesn't support structured output well, we might need a fallback.
        # But ChatOpenAI (and Ollama via proxy) usually support it.
        try:
            planner_llm = llm.with_structured_output(Plan, include_raw=True)
            chain = prompt | planner_llm
            response = chain.invoke({
                "messages": state["messages"],
                "plan": state.get("plan", "No plan yet."),
                "summary": state.get("summary", "Starting..."),
                "reasoning_effort": reasoning_effort,
                "uploaded_documents_info": uploaded_docs_section
            })
            # include_raw=True returns a dict with 'raw' and 'parsed' keys
            parsed = response.get("parsed") if isinstance(response, dict) else response
            return {
                "plan": parsed.markdown_plan,
                "plan_steps": [step.dict() for step in parsed.steps]
            }
        except (ValidationError, ValueError, KeyError) as e:
            logger.error(f"Error in structured planner: {e}")
            logger.warning("Falling back to unstructured planning mode")
            # Fallback to simple markdown if structured output fails
            chain = prompt | llm
            response = chain.invoke({
                "messages": state["messages"],
                "plan": state.get("plan", "No plan yet."),
                "summary": state.get("summary", "Starting..."),
                "reasoning_effort": reasoning_effort,
                "uploaded_documents_info": uploaded_docs_section
            })
            # Return a minimal plan structure for the fallback case
            return {
                "plan": response.content,
                "plan_steps": [{"title": "Task in progress", "description": response.content[:200], "status": "in_progress"}]
            }

    def agent(state: AgentState):
        # Build uploaded documents section if any
        uploaded_docs_section = ""
        uploaded_docs = state.get("uploaded_documents", [])
        logger.info(f"DEBUG: Agent node received {len(uploaded_docs)} uploaded documents in state")
        if uploaded_docs:
            uploaded_docs_section = "\n\nUPLOADED DOCUMENTS:\nThe user has already provided the following documents for this task:\n"
            for doc in uploaded_docs:
                uploaded_docs_section += f"- {doc['sandbox_path']}"
                if doc.get('description'):
                    uploaded_docs_section += f" ({doc['description']})"
                uploaded_docs_section += "\n"
            uploaded_docs_section += "\nIMPORTANT: These files are already available in the sandbox. You can use the 'read_file' tool to access them directly. DO NOT ask the user to upload them again or provide file paths."
            logger.info("DEBUG: Agent system prompt includes uploaded docs section")

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an AI agent controlling a Ubuntu environment. Your primary workspace is /workspace. "
                "You should create files and perform operations within this directory unless explicitly told otherwise.\n\n"
                "Goal: {goal}\n"
                "Current Plan:\n{plan}\n"
                "{uploaded_documents_info}\n"
                "OPERATIONAL GUIDELINES:\n"
                "1. Call exactly ONE tool at a time.\n"
                "2. After each tool call, you will receive an observation. Wait for it before proceeding.\n"
                "3. IMPORTANT: Before asking the user for files or data, ALWAYS check:\n"
                "   - The 'UPLOADED DOCUMENTS' section above for pre-uploaded files\n"
                "   - Use 'list_files' to check /workspace/uploads/ directory\n"
                "   - Only if no relevant files are found, then use 'ask_user' to request them\n"
                "4. If you need clarification, missing information, or if you want the user to choose between multiple options (e.g., 'PDF or PowerPoint?'), use the 'ask_user' tool. "
                "You can optionally provide a list of 'choices' to make it easier for the user to select an option. "
                "The system will pause and wait for their response.\n"
                "5. Use 'browser_open_url' to research information, read documentation, or inspect websites directly from the sandbox.\n"
                "6. Use 'tavily_web_search' for general internet searches.\n"
                "7. IMPORTANT: Before finishing, verify that ALL steps in your plan are marked as 'completed'. If some are still 'todo' or 'in_progress', you must either complete them or update the plan via the planner.\n"
                "8. When the task is fully complete, wrap your conclusion in <final_answer> tags. "
                "For example: <final_answer>Successfully installed nodejs and created the app.</final_answer>"
            )),
            MessagesPlaceholder(variable_name="messages"),
        ])
        chain = prompt | llm_with_tools
        response = chain.invoke({
            "goal": state["messages"][0].content,
            "plan": state.get("plan", ""),
            "uploaded_documents_info": uploaded_docs_section,
            "messages": state["messages"]
        })
        return {"messages": [response]}

    def check_completion(state: AgentState):
        """Check if the agent tried to finish while steps are still pending."""
        plan_steps = state.get("plan_steps", [])
        uncompleted = [s for s in plan_steps if s.get("status") != "completed"]
        
        if uncompleted:
            titles = [s.get("title") for s in uncompleted]
            msg = f"You attempted to finish the task, but the following plan steps are still not marked as 'completed': {', '.join(titles)}. Please complete them or update the plan if they are no longer relevant."
            return {"messages": [HumanMessage(content=msg)]}
        
        return {"is_finished": True}

    def should_continue(state: AgentState):
        messages = state["messages"]
        if not messages:
            return "agent"
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        
        content = last_message.content or ""
        if isinstance(last_message, AIMessage) and ("<final_answer>" in content.lower() or "TASK COMPLETED" in content.upper()):
            return "check_completion"
            
        # If no tool calls and no final answer, proceed to observer (commentary only)
        return "observer"

    def should_terminate(state: AgentState):
        """Conditional edge for check_completion node."""
        if state.get("is_finished"):
            return END
        return "observer"

    def interrupt_node(state: AgentState):
        """Dedicated node to handle user interaction using interrupt()"""
        last_message = state["messages"][-1]
        description = "Agent is waiting for your response."
        
        # If the last message was from the agent and has no tool calls, 
        # use its content as the interrupt description.
        if isinstance(last_message, AIMessage) and not last_message.tool_calls and last_message.content:
            description = last_message.content
            if len(description) > 200:
                description = description[:197] + "..."

        answer = interrupt({
            "action": "wait_for_user",
            "description": description
        })
        # The answer from Command(resume=...) is returned by interrupt()
        # We append it as a HumanMessage so the LLM sees the user's input.
        user_msg = "User approved." if answer == "approve" else str(answer)
        return {
            "messages": [HumanMessage(content=user_msg)],
            "waiting_for_user": False
        }

    def observer(state: AgentState):
        # Capture last terminal output
        last_terminal = None
        for message in reversed(state["messages"]):
            if isinstance(message, ToolMessage):
                last_terminal = message.content
                break
        
        # Refresh file tree using the flat list method (no validation required)
        file_tree = ts.list_files_flat()
        
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
    workflow.add_node("interrupt_node", interrupt_node)
    workflow.add_node("observer", observer)
    workflow.add_node("summarizer", summarizer)
    workflow.add_node("check_completion", check_completion)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "interrupt_node": "interrupt_node",
            "agent": "agent",
            "observer": "observer",
            "check_completion": "check_completion"
        }
    )
    workflow.add_conditional_edges(
        "check_completion",
        should_terminate,
        {
            END: END,
            "observer": "observer"
        }
    )
    workflow.add_edge("tools", "observer")
    workflow.add_edge("interrupt_node", "observer")
    workflow.add_edge("observer", "summarizer")
    workflow.add_edge("summarizer", "planner")

    return workflow.compile(checkpointer=checkpointer or MemorySaver())

