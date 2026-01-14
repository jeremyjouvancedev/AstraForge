import os
import json
import asyncio
import redis
import logging
import time
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
    validation_required = task_data.get("validation_required", True)
    
    logger.info(f"Starting AstraControl session {session_id} for goal: {goal}")
    
    # Ensure sandbox is provisioned
    from astraforge.sandbox.models import SandboxSession, SandboxSnapshot
    try:
        sandbox_session = SandboxSession.objects.get(id=sandbox_session_id)
        orchestrator = SandboxOrchestrator()
        orchestrator.provision(sandbox_session)
        
        # AUTO-RESTORE: If a snapshot was requested, restore it now
        if sandbox_session.restore_snapshot_id:
            logger.info(f"Restoring sandbox {sandbox_session_id} from snapshot {sandbox_session.restore_snapshot_id}")
            snapshot = SandboxSnapshot.objects.get(id=sandbox_session.restore_snapshot_id)
            orchestrator.restore_snapshot(sandbox_session, snapshot)
            
        logger.info(f"Provisioned and ready sandbox {sandbox_session_id} for session {session_id}")
    except Exception as e:
        logger.exception(f"Failed to provision/restore sandbox {sandbox_session_id}: {e}")
        async def fail_update():
            await update_session_state(session_id, status=AstraControlSession.Status.FAILED)
        asyncio.run(fail_update())
        raise

    r = redis.from_url(settings.REDIS_URL)
    config = {"configurable": {"thread_id": str(session_id)}, "recursion_limit": 100}

    # Initial state
    is_resume = task_data.get("is_resume", False)
    if is_resume:
        initial_input = {"messages": [HumanMessage(content=goal)], "is_finished": False}
    else:
        initial_input = {
            "messages": [HumanMessage(content=goal)],
            "plan": "",
            "plan_steps": [],
            "current_step": 0,
            "summary": "",
            "env_info": {},
            "screenshot": None,
            "terminal_output": None,
            "file_tree": [],
            "validation_required": validation_required,
            "is_finished": False
        }

    async def run_graph():
        from .checkpointer import get_async_checkpointer
        checkpointer = await get_async_checkpointer()
        
        # Initialize graph inside the async loop
        app = create_graph(
            model_name, 
            task_data.get("api_key") or "proxy", 
            "", # base_url not needed for direct ORM access
            sandbox_session_id, 
            provider=provider, 
            proxy_url=proxy_url,
            reasoning_check=task_data.get("reasoning_check", False),
            reasoning_effort=task_data.get("reasoning_effort", "high"),
            validation_required=validation_required,
            checkpointer=checkpointer
        )

        await update_session_state(session_id, status=AstraControlSession.Status.RUNNING)
        
        # Start or Resume the graph
        current_input = initial_input
        
        try:
            while True:
                # Check for cancellation
                session = await sync_to_async(AstraControlSession.objects.get)(id=session_id)
                if session.status == AstraControlSession.Status.CANCELLED:
                    logger.info(f"Session {session_id} was cancelled, stopping.")
                    return

                logger.info(f"DEBUG: [Iteration Start] Session {session_id} with input type: {type(current_input)}")
                is_waiting = False
                has_yielded = False
                
                async for event in app.astream(current_input, config=config):
                    has_yielded = True
                    # Clear input as soon as we start receiving events for it
                    current_input = None
                    
                    for node_name, node_output in event.items():
                        logger.info(f"DEBUG: [Node: {node_name}] Processing event")
                        
                        if node_name == "__interrupt__":
                            logger.info(f"DEBUG: Received __interrupt__ event with {len(node_output)} interrupts")
                            is_waiting = True
                            continue

                        if not isinstance(node_output, dict):
                            logger.info(f"DEBUG: Node {node_name} output is not a dict, skipping processing: {type(node_output)}")
                            continue

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
                                    
                                    content = m.content
                                    if isinstance(content, str):
                                        content = content.replace("<final_answer>", "").replace("</final_answer>", "").strip()
                                    
                                    processed_output[k].append({
                                        "role": role,
                                        "content": content,
                                        "tool_calls": tool_calls
                                    })
                            else:
                                processed_output[k] = v
                        
                        await update_session_state(session_id, event={node_name: processed_output})

                # Check state after polling
                snapshot = await app.aget_state(config)
                
                active_interrupts = []
                for task in snapshot.tasks:
                    if task.interrupts:
                        active_interrupts.extend(task.interrupts)
                
                if active_interrupts:
                    is_waiting = True
                
                if is_waiting:
                    interrupt_payload = {
                        "action": "wait_for_user",
                        "description": "Manual approval required",
                        "timestamp": int(time.time() * 1000)
                    }
                    
                    if active_interrupts:
                        last_interrupt = active_interrupts[-1]
                        val = getattr(last_interrupt, "value", last_interrupt)
                        if isinstance(val, dict):
                            interrupt_payload.update(val)
                    
                    await update_session_state(session_id, status=AstraControlSession.Status.PAUSED, event={
                        "interrupt": interrupt_payload
                    })
                    
                    resume_key = f"astra_control_resume_{session_id}"
                    msg = None
                    while not msg:
                        res = r.blpop(resume_key, timeout=2)
                        if res:
                            _, msg = res
                        session = await sync_to_async(AstraControlSession.objects.get)(id=session_id)
                        if session.status in [AstraControlSession.Status.FAILED, AstraControlSession.Status.CANCELLED]:
                            return

                    user_msg = msg.decode("utf-8")
                    if user_msg == "cancel":
                        return
                    if user_msg == "user_done":
                        user_msg = "approve"
                    
                    current_input = Command(resume=user_msg)
                    await update_session_state(session_id, status=AstraControlSession.Status.RUNNING)
                    continue
                else:
                    if not snapshot.next:
                        break
                    current_input = None
                    continue

            # AUTO-SAVE: Capture final snapshot before success
            try:
                logger.info(f"Taking final auto-snapshot for session {session_id}")
                snapshot = orchestrator.create_snapshot(sandbox_session, label=f"Auto-save: {goal[:50]}")
                session = await sync_to_async(AstraControlSession.objects.get)(id=session_id)
                session.last_snapshot_id = snapshot.id
                await sync_to_async(session.save)(update_fields=["last_snapshot_id", "updated_at"])
            except Exception as snap_err:
                logger.warning(f"Failed to take final auto-snapshot: {snap_err}")

            # Extract final answer for summary if available
            final_summary = "Task completed successfully."
            graph_state = await app.aget_state(config)
            if graph_state.values and "messages" in graph_state.values:
                last_msg = graph_state.values["messages"][-1]
                if hasattr(last_msg, "content") and "<final_answer>" in last_msg.content.lower():
                    import re
                    match = re.search(r"<final_answer>(.*?)</final_answer>", last_msg.content, re.DOTALL | re.IGNORECASE)
                    if match:
                        final_summary = match.group(1).strip()

            await update_session_state(session_id, status=AstraControlSession.Status.COMPLETED, event={
                "agent": {
                    "is_finished": True,
                    "summary": final_summary
                }
            })

        except Exception as e:
            logger.exception(f"Error in AstraControl session {session_id}: {e}")
            try:
                snapshot = orchestrator.create_snapshot(sandbox_session, label=f"Failure-snapshot: {goal[:50]}")
                session = await sync_to_async(AstraControlSession.objects.get)(id=session_id)
                session.last_snapshot_id = snapshot.id
                await sync_to_async(session.save)(update_fields=["last_snapshot_id", "updated_at"])
            except:
                pass
            await update_session_state(session_id, status=AstraControlSession.Status.FAILED)
            raise

    try:
        asyncio.run(run_graph())
    except Exception as e:
        logger.error(f"Task wrapper caught exception: {e}")
        raise