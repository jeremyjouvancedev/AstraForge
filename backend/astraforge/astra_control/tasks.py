import os
import json
import asyncio
import redis
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from asgiref.sync import sync_to_async
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from .graph import create_graph
from .state import AgentState
from .models import AstraControlSession
from astraforge.sandbox.services import SandboxOrchestrator

logger = logging.getLogger(__name__)

@sync_to_async
def update_session_state(session_id, event=None, status=None):
    """Update AstraControlSession in the database and publish to Redis for streaming."""
    try:
        session = AstraControlSession.objects.get(id=session_id)
        if status:
            session.status = status
        
        if event:
            if not isinstance(session.state, dict):
                session.state = {}
            events = session.state.get("events", [])
            events.append(event)
            session.state["events"] = events
        
        session.updated_at = timezone.now()
        session.save()
        
        # Publish to Redis for real-time streaming
        if event or status:
            r = redis.from_url(settings.REDIS_URL)
            channel = f"astra_control_stream_{session_id}"
            if event:
                r.publish(channel, json.dumps(event))
            if status:
                r.publish(channel, json.dumps({"status": status}))
                
    except AstraControlSession.DoesNotExist:
        logger.error(f"AstraControlSession {session_id} not found during update")
    except Exception as e:
        logger.exception(f"Error updating session {session_id}: {e}")

@shared_task(bind=True, name="astraforge.astra_control.run_session")
def run_astra_control_session(self, task_data: dict):
    """Celery task to run an AstraControl session."""
    session_id = task_data["session_id"]
    goal = task_data["goal"]
    sandbox_session_id = task_data["sandbox_session_id"]
    provider = task_data.get("provider") or os.getenv("LLM_PROVIDER", "openai")
    
    # Use module-specific default for model name
    default_model = "devstral-small-2:24b" if provider == "ollama" else os.getenv("LLM_MODEL", "gpt-4o")
    model_name = task_data.get("model") or default_model
    
    proxy_url = os.getenv("LLM_PROXY_URL")
    
    logger.info(f"Starting AstraControl session {session_id} for goal: {goal}")
    
    # Ensure sandbox is provisioned
    from astraforge.sandbox.models import SandboxSession
    try:
        sandbox_session = SandboxSession.objects.get(id=sandbox_session_id)
        SandboxOrchestrator().provision(sandbox_session)
        logger.info(f"Provisioned sandbox {sandbox_session_id} for session {session_id}")
    except Exception as e:
        logger.exception(f"Failed to provision sandbox {sandbox_session_id}: {e}")
        async def fail_update():
            await update_session_state(session_id, status=AstraControlSession.Status.FAILED)
        asyncio.run(fail_update())
        raise

    # Initialize graph
    app = create_graph(
        model_name, 
        task_data.get("api_key") or "proxy", 
        "", # base_url not needed for direct ORM access
        sandbox_session_id, 
        provider=provider, 
        proxy_url=proxy_url,
        reasoning_check=task_data.get("reasoning_check", False),
        reasoning_effort=task_data.get("reasoning_effort", "high")
    )
    
    # Initial state
    initial_state = {
        "messages": [HumanMessage(content=goal)],
        "plan": "",
        "plan_steps": [],
        "current_step": 0,
        "summary": "",
        "env_info": {},
        "screenshot": None,
        "terminal_output": None,
        "file_tree": [],
        "is_finished": False
    }
    
    r = redis.from_url(settings.REDIS_URL)
    config = {"configurable": {"thread_id": str(session_id)}, "recursion_limit": 100}

    async def run_graph():
        await update_session_state(session_id, status=AstraControlSession.Status.RUNNING)
        
        # Start or Resume the graph
        current_input = initial_state
        
        while True:
            is_waiting = False
            async for event in app.astream(current_input, config=config):
                for node_name, node_output in event.items():
                    # ... (rest of the processing)
                    # (I'll just replace the whole loop for safety)
                    logger.info(f"DEBUG: [Node: {node_name}] Processing event for session {session_id}")
                    
                    if not isinstance(node_output, dict):
                        logger.info(f"DEBUG: Node {node_name} output is not a dict, skipping processing: {type(node_output)}")
                        continue

                    # If we see 'wait_for_user' in output (legacy) or if it's the interrupt_node
                    if node_name == "interrupt_node":
                        is_waiting = True
                    
                    processed_output = {}
                    for k, v in node_output.items():
                        if k == "messages":
                            processed_output[k] = []
                            for m in v:
                                role = "assistant" if isinstance(m, AIMessage) else "user" if isinstance(m, HumanMessage) else "tool"
                                tool_calls = getattr(m, "tool_calls", [])
                                logger.info(f"DEBUG:   - Role: {role}")
                                if m.content:
                                    logger.info(f"DEBUG:     Content: {m.content[:200]}{'...' if len(m.content) > 200 else ''}")
                                if tool_calls:
                                    logger.info(f"DEBUG:     Tool Calls: {json.dumps(tool_calls)}")
                                
                                processed_output[k].append({
                                    "role": role,
                                    "content": m.content,
                                    "tool_calls": tool_calls
                                })
                        else:
                            processed_output[k] = v
                    
                    # Update DB and Publish to Redis per node
                    await update_session_state(session_id, event={node_name: processed_output})

            # After polling, we clear the input so it doesn't get repeated
            current_input = None

            # Check if we hit an interrupt
            snapshot = await app.aget_state(config)
            
            # Dynamic interrupts via interrupt() surface in snapshot.values['__interrupt__']
            # or in snapshot.next if they are static breakpoints.
            interrupts = snapshot.values.get("__interrupt__", [])
            if interrupts or snapshot.next:
                is_waiting = True

            if is_waiting:
                # Extract details from dynamic interrupt if present
                interrupt_reason = "Manual approval required"
                if interrupts:
                    # interrupts is typically a list of Interrupt objects
                    last_interrupt = interrupts[-1]
                    # The value is what we passed to interrupt()
                    if hasattr(last_interrupt, "value") and isinstance(last_interrupt.value, dict):
                        interrupt_reason = last_interrupt.value.get("description", interrupt_reason)
                        action_type = last_interrupt.value.get("action")
                        logger.info(f"DEBUG: Graph interrupted for {action_type}: {interrupt_reason}")

                await update_session_state(session_id, status=AstraControlSession.Status.PAUSED)
                resume_key = f"astra_control_resume_{session_id}"
                r.delete(resume_key)
                
                logger.info(f"Blocking for resume signal on {resume_key}")
                _, msg = r.brpop(resume_key)
                user_msg = msg.decode("utf-8")
                logger.info(f"Session {session_id} received resume signal: {user_msg}")
                
                # Normalize user message
                if user_msg == "user_done":
                    # For shell/file approval, 'user_done' means 'approve'
                    user_msg = "approve"
                
                # If we are resuming from a dynamic interrupt, we use Command(resume=...)
                if interrupts:
                    current_input = Command(resume=user_msg)
                    # We also inject a HumanMessage to the state for conversation history 
                    # ONLY if it was a generic wait_for_user, not a tool approval.
                    if any(i.value.get("action") == "wait_for_user" for i in interrupts if hasattr(i, "value") and isinstance(i.value, dict)):
                        actual_human_text = "User has finished manual intervention." if user_msg == "approve" else user_msg
                        await app.aupdate_state(config, {"messages": [HumanMessage(content=actual_human_text)]})
                else:
                    # Static breakpoint (legacy or tools breakpoint if still active)
                    current_input = None 
                
                await update_session_state(session_id, status=AstraControlSession.Status.RUNNING)
                continue
            else:
                # Graph finished naturally
                break
    
    try:
        asyncio.run(run_graph())

        async def final_update():
            await update_session_state(session_id, status=AstraControlSession.Status.COMPLETED)
        asyncio.run(final_update())
    except Exception as e:
        logger.exception(f"Error in AstraControl session {session_id}: {e}")
        async def error_update():
            await update_session_state(session_id, status=AstraControlSession.Status.FAILED)
        asyncio.run(error_update())
        raise