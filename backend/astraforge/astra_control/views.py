import json
import os
import redis
import subprocess
import time
import logging
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from .models import AstraControlSession
from .serializers import AstraControlSessionSerializer
from astraforge.sandbox.models import SandboxSession
from astraforge.interfaces.rest.renderers import EventStreamRenderer

logger = logging.getLogger(__name__)

class AstraControlSessionViewSet(viewsets.ModelViewSet):
    queryset = AstraControlSession.objects.all()
    serializer_class = AstraControlSessionSerializer
    renderer_classes = [JSONRenderer, EventStreamRenderer]

    def perform_create(self, serializer):
        # Auto-create a sandbox session if not provided
        sandbox_session_id = self.request.data.get("sandbox_session_id")
        if not sandbox_session_id:
            sandbox_session = SandboxSession.objects.create(
                user=self.request.user,
                image=settings.ASTRA_CONTROL_IMAGE,
                mode=SandboxSession.Mode.DOCKER
            )
        else:
            sandbox_session = SandboxSession.objects.get(id=sandbox_session_id, user=self.request.user)
        
        session = serializer.save(user=self.request.user, sandbox_session=sandbox_session)
        
        provider = self.request.data.get("provider") or os.getenv("LLM_PROVIDER", "openai")
        # Default model for this module is devstral-small-2:24b when using ollama
        default_model = "devstral-small-2:24b" if provider == "ollama" else os.getenv("LLM_MODEL", "gpt-4o")
        
        task_data = {
            "session_id": str(session.id),
            "goal": session.goal,
            "sandbox_session_id": str(sandbox_session.id),
            "model": self.request.data.get("model") or default_model,
            "provider": provider,
            "reasoning_check": self.request.data.get("reasoning_check"),
            "reasoning_effort": self.request.data.get("reasoning_effort")
        }
        
        try:
            from .tasks import run_astra_control_session
            run_astra_control_session.apply_async(
                args=[task_data],
                queue="astraforge.astra_control"
            )
            session.status = AstraControlSession.Status.RUNNING
            session.save()
            logger.info(f"Triggered Celery task for session {session.id}")
        except Exception as e:
            session.status = AstraControlSession.Status.FAILED
            session.save()
            logger.error(f"Failed to push astra control task: {e}")

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        session = self.get_object()
        r = redis.from_url(settings.REDIS_URL)
        r.lpush(f"astra_control_resume_{session.id}", "user_done")
        return Response({"status": "resume signal sent"})

    @action(detail=True, methods=['post'])
    def log_event(self, request, pk=None):
        session = self.get_object()
        event = request.data.get("event")
        status_update = request.data.get("status")
        
        if status_update:
            session.status = status_update
        
        if event:
            if not isinstance(session.state, dict):
                session.state = {}
            events = session.state.get("events", [])
            events.append(event)
            session.state["events"] = events
        
        session.save()
        return Response({"status": "ok"})

    @action(detail=True, methods=["get"])
    def stream(self, request, pk=None):
        logger.info(f"DEBUG: stream action called for session {pk}")
        session = self.get_object()
        
        def event_stream():
            logger.info(f"DEBUG: event_stream generator started for session {session.id}")
            r = redis.from_url(settings.REDIS_URL)
            pubsub = r.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f"astra_control_stream_{session.id}")
            
            # Initial handshake
            yield "event: message\ndata: " + json.dumps({"type": "heartbeat", "message": "stream_ready"}) + "\n\n"

            # Initial status
            initial_data = json.dumps({'status': session.status})
            yield f"event: message\ndata: {initial_data}\n\n"
            
            last_heartbeat = time.time()
            try:
                while True:
                    message = pubsub.get_message()
                    if message:
                        if message["type"] == "message":
                            data = message["data"].decode("utf-8")
                            logger.debug(f"DEBUG: received message from redis for session {session.id}: {data}")
                            yield f"event: message\ndata: {data}\n\n"
                    
                    now = time.time()
                    if now - last_heartbeat > 15.0:
                        yield "event: message\ndata: " + json.dumps({"type": "heartbeat"}) + "\n\n"
                        last_heartbeat = now
                    
                    if not message:
                        time.sleep(0.5)
                    
                    # Check if session is finished
                    session.refresh_from_db()
                    if session.status in [AstraControlSession.Status.COMPLETED, AstraControlSession.Status.FAILED]:
                        logger.info(f"DEBUG: session {session.id} finished with status {session.status}")
                        final_data = json.dumps({'status': session.status})
                        yield f"event: message\ndata: {final_data}\n\n"
                        break
            except Exception as e:
                logger.error(f"DEBUG: exception in event_stream for session {session.id}: {e}")
            finally:
                logger.info(f"DEBUG: event_stream generator closing for session {session.id}")
                pubsub.unsubscribe()
        
        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response