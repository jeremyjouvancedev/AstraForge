import json
import os
import redis
import time
import logging
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import MultiPartParser, FormParser
from .models import AstraControlSession
from .serializers import AstraControlSessionSerializer, DocumentUploadSerializer
from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator
from astraforge.interfaces.rest.renderers import EventStreamRenderer

logger = logging.getLogger(__name__)

class AstraControlSessionViewSet(viewsets.ModelViewSet):
    queryset = AstraControlSession.objects.all()
    serializer_class = AstraControlSessionSerializer
    renderer_classes = [JSONRenderer, EventStreamRenderer]

    def perform_create(self, serializer):
        # Find latest session snapshot for auto-restore
        latest_snapshot_id = None
        latest_session = AstraControlSession.objects.filter(
            user=self.request.user,
            status=AstraControlSession.Status.COMPLETED
        ).order_by("-created_at").first()
        
        if latest_session and latest_session.last_snapshot_id:
            latest_snapshot_id = latest_session.last_snapshot_id
            logger.info(f"Auto-restoring from latest snapshot {latest_snapshot_id} of session {latest_session.id}")
        elif latest_session and latest_session.state:
            # Fallback to searching snapshots if last_snapshot_id is missing (legacy sessions)
            from astraforge.sandbox.models import SandboxSnapshot
            snapshot = SandboxSnapshot.objects.filter(
                session=latest_session.sandbox_session,
                label__icontains="Auto-save"
            ).first()
            if snapshot:
                latest_snapshot_id = snapshot.id
                logger.info(f"Auto-restoring from legacy snapshot {latest_snapshot_id} of session {latest_session.id}")

        # Auto-create a sandbox session if not provided
        sandbox_session_id = self.request.data.get("sandbox_session_id")
        if not sandbox_session_id:
            sandbox_session = SandboxSession.objects.create(
                user=self.request.user,
                image=settings.ASTRA_CONTROL_IMAGE,
                mode=SandboxSession.Mode.DOCKER,
                restore_snapshot_id=latest_snapshot_id
            )
        else:
            sandbox_session = SandboxSession.objects.get(id=sandbox_session_id, user=self.request.user)
        
        session = serializer.save(user=self.request.user, sandbox_session=sandbox_session)
        
        provider = self.request.data.get("provider") or os.getenv("LLM_PROVIDER", "openai")
        # Default model for this module
        if provider == "ollama":
            default_model = "devstral-small-2:24b"
        elif provider == "azure_openai":
            # For Azure OpenAI, model should come from frontend (deployment name)
            default_model = None  # Force user to specify deployment in frontend
        else:
            default_model = os.getenv("LLM_MODEL", "gpt-4o")

        task_data = {
            "session_id": str(session.id),
            "goal": session.goal,
            "sandbox_session_id": str(sandbox_session.id),
            "model": self.request.data.get("model") or default_model,
            "provider": provider,
            "reasoning_check": self.request.data.get("reasoning_check"),
            "reasoning_effort": self.request.data.get("reasoning_effort"),
            "validation_required": self.request.data.get("validation_required", True)
        }

        # Store configuration in session state for resume
        if not isinstance(session.state, dict):
            session.state = {}
        session.state["config"] = {
            "provider": provider,
            "model": task_data["model"],
            "reasoning_check": task_data["reasoning_check"],
            "reasoning_effort": task_data["reasoning_effort"]
        }
        session.save()
        
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
        r.rpush(f"astra_control_resume_{session.id}", "user_done")
        return Response({"status": "resume signal sent"})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        session = self.get_object()
        if session.status in [AstraControlSession.Status.RUNNING, AstraControlSession.Status.PAUSED]:
            session.status = AstraControlSession.Status.CANCELLED
            session.save()
            # If paused, we need to unblock the blpop
            r = redis.from_url(settings.REDIS_URL)
            r.rpush(f"astra_control_resume_{session.id}", "cancel")
            return Response({"status": "cancel signal sent"})
        return Response({"status": "session not running"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def message(self, request, pk=None):
        session = self.get_object()
        message_text = request.data.get("message")
        if not message_text:
            return Response({"error": "message is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Log the user message as an event
        event = {
            "human_input": {
                "message": message_text,
                "timestamp": int(time.time() * 1000)
            }
        }
        if not isinstance(session.state, dict):
            session.state = {}
        events = session.state.get("events", [])
        events.append(event)
        session.state["events"] = events
        session.save()
        
        # Publish the event to Redis for immediate streaming
        r = redis.from_url(settings.REDIS_URL)
        channel = f"astra_control_stream_{session.id}"
        r.publish(channel, json.dumps(event))

        # If paused, resume with the message
        if session.status == AstraControlSession.Status.PAUSED:
            r.rpush(f"astra_control_resume_{session.id}", message_text)
            return Response({"status": "message sent to paused session"})
        
        # If finished or cancelled, restart the task
        if session.status in [AstraControlSession.Status.COMPLETED, AstraControlSession.Status.FAILED, AstraControlSession.Status.CANCELLED]:
            session.status = AstraControlSession.Status.RUNNING
            session.save()
            
            # Re-trigger task
            from .tasks import run_astra_control_session
            
            # Retrieve stored config or use request data
            stored_config = session.state.get("config", {}) if isinstance(session.state, dict) else {}
            provider = request.data.get("provider") or stored_config.get("provider") or os.getenv("LLM_PROVIDER", "openai")
            model = request.data.get("model") or stored_config.get("model")
            reasoning_check = request.data.get("reasoning_check")
            if reasoning_check is None:
                reasoning_check = stored_config.get("reasoning_check")
            reasoning_effort = request.data.get("reasoning_effort") or stored_config.get("reasoning_effort", "high")
            
            task_data = {
                "session_id": str(session.id),
                "goal": message_text,
                "is_resume": True,
                "sandbox_session_id": str(session.sandbox_session.id),
                "provider": provider,
                "model": model,
                "reasoning_check": reasoning_check,
                "reasoning_effort": reasoning_effort,
                "validation_required": request.data.get("validation_required", True)
            }
            
            run_astra_control_session.apply_async(
                args=[task_data],
                queue="astraforge.astra_control"
            )
            return Response({"status": "session restarted with new message"})
            
        return Response({"status": "session is busy"}, status=status.HTTP_400_BAD_REQUEST)

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

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_document(self, request, pk=None):
        """Upload a document to the session's sandbox and track it in session state."""
        session = self.get_object()

        # Validate sandbox session exists and is accessible
        if not session.sandbox_session:
            return Response(
                {"error": "No sandbox session associated with this Astra Control session"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate sandbox is ready for execution
        if session.sandbox_session.status != SandboxSession.Status.READY:
            return Response(
                {"error": f"Sandbox is not ready for execution. Current status: {session.sandbox_session.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate max documents (5 documents per session)
        if not isinstance(session.state, dict):
            session.state = {}
        documents = session.state.get("documents", [])
        if len(documents) >= 5:
            return Response(
                {"error": "Maximum 5 documents per session. Delete existing documents first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = DocumentUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data['file']
        description = serializer.validated_data.get('description', '')

        # Upload to sandbox at /workspace/uploads/
        sandbox_path = f"/workspace/uploads/{uploaded_file.name}"

        try:
            orchestrator = SandboxOrchestrator()
            file_content = uploaded_file.read()

            # Upload file to sandbox
            orchestrator.upload_bytes(session.sandbox_session, sandbox_path, file_content)

            # Track document in session state
            document_metadata = {
                "filename": uploaded_file.name,
                "sandbox_path": sandbox_path,
                "description": description,
                "size_bytes": uploaded_file.size,
                "content_type": uploaded_file.content_type,
                "uploaded_at": int(time.time() * 1000)
            }
            documents.append(document_metadata)
            session.state["documents"] = documents
            session.save()

            # Publish event to Redis for real-time streaming
            event = {
                "document_uploaded": {
                    "filename": uploaded_file.name,
                    "path": sandbox_path,
                    "description": description,
                    "timestamp": document_metadata["uploaded_at"]
                }
            }
            r = redis.from_url(settings.REDIS_URL)
            channel = f"astra_control_stream_{session.id}"
            r.publish(channel, json.dumps(event))

            # If session is paused, auto-resume with notification
            if session.status == AstraControlSession.Status.PAUSED:
                notification_msg = f"New document uploaded: {uploaded_file.name}"
                if description:
                    notification_msg += f" - {description}"
                notification_msg += f"\nPath: {sandbox_path}"

                # Store the notification as a human input event
                notification_event = {
                    "human_input": {
                        "message": notification_msg,
                        "timestamp": document_metadata["uploaded_at"]
                    }
                }
                events = session.state.get("events", [])
                events.append(notification_event)
                session.state["events"] = events
                session.save()

                # Publish notification
                r.publish(channel, json.dumps(notification_event))

                # Resume the session
                r.rpush(f"astra_control_resume_{session.id}", notification_msg)

                logger.info(f"Document uploaded and session {session.id} auto-resumed")

                return Response({
                    "status": "success",
                    "message": "Document uploaded and session resumed",
                    "document": document_metadata
                }, status=status.HTTP_201_CREATED)

            logger.info(f"Document uploaded to session {session.id}: {uploaded_file.name}")

            return Response({
                "status": "success",
                "message": "Document uploaded successfully",
                "document": document_metadata
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception(f"Failed to upload document to session {session.id}: {e}")
            return Response(
                {"error": f"Failed to upload document: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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