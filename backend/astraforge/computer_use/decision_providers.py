import json
import os
from dataclasses import dataclass
from typing import Any, Iterable, Protocol, Literal, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from pydantic import BaseModel, Field

from .protocol import (
    ComputerCall,
    ComputerCallAction,
    ComputerCallMeta,
    DecisionRequest,
    DecisionResponse,
    PendingSafetyCheck,
    ensure_call_id,
    ensure_response_id,
    new_call_id,
)


class ClickAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["ClickAction"] = "ClickAction"
    type: Literal["click", "double_click"] = Field(..., description="The type of click action.")
    index: Optional[int] = Field(None, description="Element index from the DOM tree. Preferred over coordinates.")
    x: Optional[int] = Field(None, description="X coordinate.")
    y: Optional[int] = Field(None, description="Y coordinate.")
    button: Optional[str] = Field("left", description="Mouse button (left, right, middle).")

class InputAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["InputAction"] = "InputAction"
    type: Literal["input", "type"] = Field(..., description="The type of input action.")
    index: Optional[int] = Field(None, description="Element index from the DOM tree.")
    text: str = Field(..., description="The text to type.")
    submit: bool = Field(False, description="Whether to press Enter after typing.")

class NavigateAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["NavigateAction"] = "NavigateAction"
    type: Literal["navigate", "visit_url"] = Field(..., description="The type of navigation action.")
    url: str = Field(..., description="The URL to visit.")

class TavilySearchAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["TavilySearchAction"] = "TavilySearchAction"
    type: Literal["tavily_search"] = Field(..., description="Search the web using Tavily API (Programmatic). This is the only way to search.")
    query: str = Field(..., description="The search query.")
    search_depth: Optional[Literal["basic", "advanced"]] = Field("basic", description="The depth of the search.")

class ScrollAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["ScrollAction"] = "ScrollAction"
    type: Literal["scroll"] = Field(..., description="The scroll action.")
    scroll_dx: Optional[int] = Field(0, description="Horizontal scroll amount.")
    scroll_dy: Optional[int] = Field(0, description="Vertical scroll amount. Positive scrolls down.")

class KeypressAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["KeypressAction"] = "KeypressAction"
    type: Literal["keypress", "send_keys"] = Field(..., description="The keypress action.")
    keys: list[str] = Field(..., description="List of keys to press (e.g., ['Enter', 'Ctrl+C']).")

class WaitAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["WaitAction"] = "WaitAction"
    type: Literal["wait"] = Field(..., description="The wait action.")
    seconds: float = Field(..., description="Duration to wait in seconds.")

class TerminateAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["TerminateAction"] = "TerminateAction"
    type: Literal["terminate"] = Field(..., description="Terminate the task when the goal is achieved or if it's impossible.")
    final_response: Optional[str] = Field(None, description="The final answer or summary of the completed task. MUST be provided when the task is successful.")

class BackAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["BackAction"] = "BackAction"
    type: Literal["back", "go_back"] = Field(..., description="Navigate back in history.")

class GenericAction(BaseModel):
    reasoning: str = Field(..., description="The reasoning for this action.")
    tool_name: Literal["GenericAction"] = "GenericAction"
    type: Literal[
        "upload_file", "find_text", "evaluate", "switch", "close", 
        "extract", "screenshot", "dropdown_options", "select_dropdown", 
        "write_file", "read_file", "replace_file"
    ]
    index: Optional[int] = None
    text: Optional[str] = None
    path: Optional[str] = None
    script: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None

# Action Tools list for binding
ACTION_TOOLS = [
    ClickAction, InputAction, NavigateAction, TavilySearchAction,
    ScrollAction, KeypressAction, WaitAction, TerminateAction,
    BackAction, GenericAction
]


class DecisionProvider(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResponse:  # pragma: no cover - protocol
        ...


@dataclass(slots=True)
class ScriptedDecisionProvider:
    script: list[dict[str, Any]]

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        index = request.step_index
        if index < len(self.script):
            entry = self.script[index]
        else:
            entry = {"action": {"type": "terminate"}}

        call = _call_from_entry(entry)
        call.action.validate()
        call = ensure_call_id(call)
        response_id = ensure_response_id(entry.get("response_id"))
        reasoning_summary = None
        meta = entry.get("meta")
        if isinstance(meta, dict):
            reasoning_summary = meta.get("reasoning_summary")
        return DecisionResponse(
            response_id=response_id,
            computer_call=call,
            reasoning_summary=reasoning_summary,
        )


@dataclass(slots=True)
class DeepAgentDecisionProvider:
    provider: str = "openai"
    model_name: str = "gpt-4o"
    temperature: float = 0.0
    reasoning_effort: str = "high"
    reasoning_check: bool = True

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        if self.provider == "ollama":
            from langchain_ollama import ChatOllama
            model_kwargs = _build_ollama_model_kwargs(
                self.model_name, self.reasoning_effort, self.reasoning_check
            )
            model = ChatOllama(
                model=self.model_name,
                temperature=self.temperature,
                base_url=os.getenv("OLLAMA_BASE_URL") or None,
                model_kwargs=model_kwargs,
            )
        else:
            model = ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL") or None,
            )

        system_prompt = (
            "You are a browser automation agent. Your goal is: {goal}\n\n"
            "You will be provided with a screenshot and a simplified DOM tree of the current page.\n"
            "Call one of the provided tools to perform the next action.\n"
            "Supported tools: TavilySearchAction, NavigateAction, ClickAction, InputAction, ScrollAction, KeypressAction, BackAction, WaitAction, TerminateAction.\n\n"
            "Tool Definitions:\n"
            "- TavilySearchAction: Search the web using Tavily API. Use this for all web discovery.\n"
            "- NavigateAction: Visit a specific URL returned by the search.\n"
            "- ClickAction: Click an element by its index from the DOM tree. Fallback: coordinates.\n"
            "- InputAction: Type text into an element. Set 'submit': true to press Enter afterwards.\n"
            "- ScrollAction: Scroll the page. Positive dy scrolls down.\n"
            "- KeypressAction: Send specific key presses.\n"
            "- BackAction: Navigate back in history.\n"
            "- WaitAction: Wait for a specified duration.\n"
            "- TerminateAction: Signals that the task is complete. When the task is successful, provide the final answer or summary in the 'final_response' field.\n\n"
            "STRATEGY:\n"
            "1. If the current URL is 'about:blank' or empty, you MUST start by using 'TavilySearchAction' to find relevant information.\n"
            "2. Always prefer 'TavilySearchAction' over browsing search engine UIs (Google, Bing, etc.) to avoid CAPTCHAs.\n"
            "3. Change strategy if an action is twice executed with the same behavior on the same URL.\n\n"
            "CAPTCHA HANDLING:\n"
            "If a CAPTCHA or bot detection is identified, you MUST find an alternative URL or different search query to get the information using TavilySearchAction. Avoid getting stuck on bot-protected pages.\n\n"
            "CRITICAL: You MUST respond ONLY with a tool call. Do not provide conversational text."
        ).format(goal=request.goal)

        messages = [SystemMessage(content=system_prompt)]
        
        # We might need to carry over the last screenshot if the current observation is empty (e.g. after a search)
        last_screenshot_b64 = None
        last_url = None

        # Reconstruct conversation history from trace
        for item in request.history:
            if item.get("type") == "computer_call":
                action = item.get("action", {})
                call_id = item.get("call_id")
                
                tool_name = action.get("tool_name") or "GenericAction"
                tool_call = {
                    "name": tool_name,
                    "args": action,
                    "id": call_id,
                    "type": "tool_call"
                }
                messages.append(AIMessage(content="", tool_calls=[tool_call]))
                
            elif item.get("type") == "computer_call_output":
                call_id = item.get("call_id")
                output = item.get("output", {})
                
                content_blocks = []
                exec_data = output.get("execution", {})
                status = exec_data.get("status")
                url = output.get("url")
                
                # Track latest valid screenshot and URL in history
                if output.get("screenshot_b64"):
                    last_screenshot_b64 = output["screenshot_b64"]
                    last_url = url

                text_content = f"URL: {url}\nStatus: {status}"
                if exec_data.get("captcha_detected"):
                    text_content += "\nCRITICAL: CAPTCHA or Bot Detection identified on this page."
                if status == "error":
                    text_content += f"\nError: {exec_data.get('error_message')}"
                
                content_blocks.append({"type": "text", "text": text_content})
                
                # NOTE: We skip historical screenshots to keep the context size manageable.
                # Only the latest screenshot from request.observation is included below.
                
                messages.append(ToolMessage(content=content_blocks, tool_call_id=call_id))

        content = []
        content.append({"type": "text", "text": f"Current URL: {request.observation.url}"})
        if request.observation.execution.captcha_detected:
            content.append({"type": "text", "text": "CRITICAL: CAPTCHA detected! Consider using an alternative URL or search query."})
        if request.observation.dom_tree:
            content.append({"type": "text", "text": f"DOM Tree:\n{request.observation.dom_tree}"})
        
        # Use current screenshot, or fallback to the last one if URL is the same and current is missing
        screenshot_to_send = request.observation.screenshot_b64
        if not screenshot_to_send and last_screenshot_b64 and request.observation.url == last_url:
            screenshot_to_send = last_screenshot_b64

        if screenshot_to_send:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot_to_send}"}
            })

        messages.append(HumanMessage(content=content))

        # Bind all action tools flattened
        tool_model = model.bind_tools(ACTION_TOOLS)
        
        # Capture debug info before invocation
        from langchain_core.messages import message_to_dict
        debug_info = {
            "messages": [message_to_dict(m) for m in messages],
            "model": self.model_name,
            "provider": self.provider
        }

        try:
            response = tool_model.invoke(messages)
            # DEBUG LOGGING
            print(f"DEBUG: LLM Response Content: {response.content}", flush=True)
            print(f"DEBUG: LLM Tool Calls: {response.tool_calls}", flush=True)
        except Exception as e:
            print(f"DEBUG: LLM Invocation Error: {e}", flush=True)
            return DecisionResponse(
                response_id=ensure_response_id(None),
                computer_call=ComputerCall(
                    call_id=new_call_id(),
                    action=ComputerCallAction(type="terminate"),
                    meta=ComputerCallMeta(done=True, reasoning_summary=f"LLM invocation failed: {str(e)}")
                ),
                debug_info=debug_info
            )
        
        action_data = {}
        reasoning = None

        if response.tool_calls:
            tool_call = response.tool_calls[0]
            action_data = tool_call.get("args", {})
            action_data["tool_name"] = tool_call.get("name")
            print(f"DEBUG: Tool Call Args: {action_data}", flush=True)
            
            # Extract reasoning
            reasoning = action_data.get("reasoning")

            # Ensure 'type' is present. If using a specific tool class, type should be in args,
            # but if something went wrong, we might infer it from tool name?
            # Pydantic models with Literal type field usually include it in the dict.
        else:
            # Fallback if tool calling failed but text was returned
            try:
                raw_text = str(response.content).strip()
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                
                # Attempt to parse as JSON
                data = json.loads(raw_text)
                action_data = data.get("action") or {} # Backward compatibility attempt
                if not action_data: 
                     # Maybe the root object IS the action if flattened?
                     # But old prompts returned {action: ...}. The new prompt asks to call tools.
                     # If it falls back to text, it might be unstructured.
                     # Let's assume if "action" key exists use it, else try to use data as action
                     if "type" in data:
                         action_data = data
                
                reasoning = data.get("reasoning")
            except Exception:
                pass

        if not action_data:
             # If we have text content but no tool calls, it's a failure to use tools
             reasoning_fallback = response.content if response.content else "LLM failed to provide valid action via tool or JSON"
             return DecisionResponse(
                response_id=ensure_response_id(None),
                computer_call=ComputerCall(
                    call_id=new_call_id(),
                    action=ComputerCallAction(type="terminate"),
                    meta=ComputerCallMeta(done=True, reasoning_summary=f"Tool call failed. LLM said: {reasoning_fallback}")
                ),
                debug_info=debug_info
            )

        # Alias search -> tavily_search for robustness
        if action_data.get("type") in ("search", "web_search"):
            action_data["type"] = "tavily_search"

        call = ComputerCall(
            call_id=new_call_id(),
            action=ComputerCallAction.from_dict(action_data),
            meta=ComputerCallMeta(
                done=(action_data.get("type") == "terminate"),
                reasoning_summary=reasoning
            )
        )
        
        # Validate locally to prevent runner crash
        try:
            call.action.validate()
        except ValueError as e:
             return DecisionResponse(
                response_id=ensure_response_id(None),
                computer_call=ComputerCall(
                    call_id=new_call_id(),
                    action=ComputerCallAction(type="terminate"),
                    meta=ComputerCallMeta(done=True, reasoning_summary=f"Generated invalid action: {str(e)}")
                ),
                debug_info=debug_info
            )

        return DecisionResponse(
            response_id=ensure_response_id(None),
            computer_call=call,
            reasoning_summary=reasoning,
            debug_info=debug_info
        )


def _format_history(history: list[dict[str, Any]]) -> str:
    lines = []
    for i, item in enumerate(history):
        if "computer_call" in item:
            call = item["computer_call"]
            action = call.get("action", {})
            action_type = action.get("type")
            details = f"type={action_type}"
            if action_type in ("click", "input"):
                details += f", index={action.get('index')}"
            if action_type == "input":
                details += f", text='{action.get('text')}'"
            lines.append(f"[Step {i+1}] Action: {details}")
        elif "computer_call_output" in item:
            output = item["computer_call_output"].get("output", {})
            exec_res = output.get("execution", {})
            status = exec_res.get("status")
            url = output.get("url", "unknown")
            lines.append(f"         Result: status={status}, url={url}")
            if status == "error":
                lines.append(f"         Error: {exec_res.get('error_message')}")
    return "\n".join(lines)


def _is_reasoning_model(model: str) -> bool:
    patterns = ["gpt-oss", "devstral", "deepseek-r1", "o1-", "o3-"]
    return any(model.lower().startswith(p) for p in patterns)


def _build_ollama_model_kwargs(model_name: str, effort: str, check: bool) -> dict[str, Any]:
    model_kwargs: dict[str, Any] = {}
    if check or _is_reasoning_model(model_name):
        if effort in {"low", "medium", "high"}:
            model_kwargs["think"] = effort
    return model_kwargs


def _call_from_entry(entry: dict[str, Any]) -> ComputerCall:
    if "computer_call" in entry:
        raw_call = entry["computer_call"] or {}
        return ComputerCall.from_dict(raw_call)

    action = ComputerCallAction.from_dict(entry.get("action") or {})
    meta = ComputerCallMeta.from_dict(entry.get("meta"))
    pending = [
        PendingSafetyCheck.from_dict(item)
        for item in (entry.get("pending_safety_checks") or [])
    ]
    return ComputerCall(
        call_id=str(entry.get("call_id") or ""),
        action=action,
        meta=meta,
        pending_safety_checks=pending,
    )


def build_policy_summary(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "allowed_domains": list(config.get("allowed_domains") or []),
        "blocked_domains": list(config.get("blocked_domains") or []),
        "approval_mode": config.get("approval_mode", "auto"),
        "allow_login": bool(config.get("allow_login", False)),
        "allow_payments": bool(config.get("allow_payments", False)),
        "allow_irreversible": bool(config.get("allow_irreversible", False)),
        "allow_credentials": bool(config.get("allow_credentials", False)),
    }


def normalize_script(raw: Iterable[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    return [dict(item) for item in raw]
        