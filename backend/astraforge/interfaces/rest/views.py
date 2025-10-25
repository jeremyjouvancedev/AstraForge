"""REST API views for AstraForge."""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
import json

from django.http import StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from astraforge.accounts.models import ApiKey
from astraforge.application import tasks as app_tasks
from astraforge.application.use_cases import ApplyPlan, GeneratePlan, SubmitRequest
from astraforge.bootstrap import container, repository
from astraforge.integrations.models import RepositoryLink
from astraforge.interfaces.rest import serializers
from astraforge.interfaces.rest.renderers import EventStreamRenderer


class RequestViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.RequestSerializer
    lookup_field = "id"

    def create(self, request, *args, **kwargs):
        if not RepositoryLink.objects.filter(user=request.user).exists():
            raise PermissionDenied("Link a project before submitting requests.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_obj = serializer.save()
        SubmitRequest(repository=repository)(request_obj)
        app_tasks.generate_spec_task.delay(str(request_obj.id))
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def list(self, request, *args, **kwargs):
        items = repository.list()
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request, id=None):
        serializer = serializers.ExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(id)
        try:
            repository.get(request_id)
        except KeyError as exc:
            raise NotFound(f"Request {request_id} not found") from exc
        app_tasks.execute_request_task.delay(
            request_id,
            serializer.validated_data.get("spec"),
        )
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    def get_object(self):
        from django.http import Http404

        request_id = self.kwargs[self.lookup_field]
        try:
            return repository.get(str(request_id))
        except KeyError as exc:  # pragma: no cover - fallback
            raise Http404(f"Request {request_id} not found") from exc


class ChatViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.ChatSerializer

    def create(self, request, *args, **kwargs):  # pragma: no cover - stub
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(serializer.validated_data["request_id"])
        container.resolve_run_log().publish(
            request_id,
            {
                "type": "user_message",
                "request_id": request_id,
                "message": serializer.validated_data["message"],
            },
        )
        return Response({"status": "received"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):  # pragma: no cover - stub
        request_id = str(pk)
        app_tasks.submit_merge_request_task.delay(request_id)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


class RunLogStreamView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [EventStreamRenderer]

    def get(self, request, pk):  # pragma: no cover - SSE placeholder
        request_id = str(pk)
        run_log = container.resolve_run_log()

        def event_stream():
            handshake = {"request_id": request_id, "type": "heartbeat", "message": "stream_ready"}
            yield "event: message\n"
            yield "data: " + json.dumps(handshake) + "\n\n"
            for event in run_log.stream(request_id):
                yield "event: message\n"
                yield "data: " + json.dumps(event) + "\n\n"

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response


class PlanViewSet(viewsets.ViewSet):  # pragma: no cover - skeleton
    permission_classes = [IsAuthenticated]

    def create(self, request):
        serializer = serializers.PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_case = GeneratePlan(
            repository=repository, executor=container.resolve_executor()
        )
        try:
            plan = use_case(str(serializer.validated_data["request_id"]))
        except KeyError as exc:  # pragma: no cover - not found
            raise NotFound(str(exc)) from exc
        response = serializers.PlanSerializer(plan)
        return Response(response.data, status=status.HTTP_200_OK)


class ExecutionViewSet(viewsets.ViewSet):  # pragma: no cover - skeleton
    permission_classes = [IsAuthenticated]

    def create(self, request):
        serializer = serializers.ExecutionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        use_case = ApplyPlan(
            repository=repository,
            executor=container.resolve_executor(),
            vcs=container.vcs_providers.resolve("gitlab"),
            provisioner=container.provisioners.resolve("k8s"),
        )
        try:
            mr_ref = use_case(
                request_id=str(serializer.validated_data["request_id"]),
                repo=serializer.validated_data["repository"],
                branch=serializer.validated_data["branch"],
            )
        except KeyError as exc:  # pragma: no cover - not found
            raise NotFound(str(exc)) from exc
        return Response({"mr_ref": mr_ref}, status=status.HTTP_202_ACCEPTED)


class ApiKeyViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = serializers.ApiKeySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ApiKey.objects.filter(user=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = serializers.ApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        api_key, raw_key = ApiKey.create_key(
            user=request.user, name=serializer.validated_data["name"]
        )
        data = serializers.ApiKeySerializer(api_key).data
        data["key"] = raw_key
        headers = {"Location": str(api_key.id)}
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, pk=None):
        try:
            api_key = ApiKey.objects.get(id=pk, user=request.user)
        except ApiKey.DoesNotExist:
            raise NotFound("API key not found") from None
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class RepositoryLinkViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = serializers.RepositoryLinkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return RepositoryLink.objects.filter(user=self.request.user).order_by("created_at")

    def perform_create(self, serializer):
        serializer.save()


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(
            {"username": user.username, "email": user.email},
            status=status.HTTP_201_CREATED,
        )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = serializers.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
        login(request, user)
        return Response(
            {"username": user.username, "email": user.email}, status=status.HTTP_200_OK
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({"username": user.username, "email": user.email})
