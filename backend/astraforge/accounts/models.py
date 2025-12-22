from __future__ import annotations

import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

IDENTITY_PROVIDER_PASSWORD = "password"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class ApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    key_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    created_at = models.DateTimeField(default=timezone.now)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    @classmethod
    def create_key(cls, *, user, name: str) -> tuple["ApiKey", str]:
        raw_key = secrets.token_urlsafe(32)
        key_hash = _hash_key(raw_key)
        instance = cls.objects.create(user=user, name=name, key_hash=key_hash)
        return instance, raw_key

    @staticmethod
    def hash_raw(raw_key: str) -> str:
        return _hash_key(raw_key)

    def verify(self, raw_key: str) -> bool:
        return secrets.compare_digest(self.key_hash, _hash_key(raw_key))

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])


class AccessStatus(models.TextChoices):
    PENDING = "pending", "Pending approval"
    APPROVED = "approved", "Approved"
    BLOCKED = "blocked", "Blocked"


class UserAccess(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="access"
    )
    identity_provider = models.CharField(
        max_length=64, default=IDENTITY_PROVIDER_PASSWORD
    )
    status = models.CharField(
        max_length=32, choices=AccessStatus.choices, default=AccessStatus.PENDING
    )
    notes = models.TextField(blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    waitlist_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "User Access"
        verbose_name_plural = "User Access"

    @classmethod
    def for_user(cls, user, identity_provider: str | None = None) -> "UserAccess":
        defaults = {
            "identity_provider": identity_provider or IDENTITY_PROVIDER_PASSWORD
        }
        access, _ = cls.objects.get_or_create(user=user, defaults=defaults)
        if (
            access.status != AccessStatus.BLOCKED
            and not access.is_approved
            and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
        ):
            access.approve()
        # Keep track of the latest provider a user authenticated with.
        if identity_provider and access.identity_provider != identity_provider:
            access.identity_provider = identity_provider
            access.save(update_fields=["identity_provider", "updated_at"])
        return access

    @property
    def is_approved(self) -> bool:
        return self.status == AccessStatus.APPROVED

    def approve(self) -> None:
        if self.status != AccessStatus.APPROVED:
            self.status = AccessStatus.APPROVED
            self.approved_at = timezone.now()
            self.save(update_fields=["status", "approved_at", "updated_at"])

    def block(self) -> None:
        if self.status != AccessStatus.BLOCKED:
            self.status = AccessStatus.BLOCKED
            self.save(update_fields=["status", "updated_at"])

    def mark_waitlist_notified(self) -> None:
        if self.waitlist_notified_at:
            return
        self.waitlist_notified_at = timezone.now()
        self.save(update_fields=["waitlist_notified_at", "updated_at"])

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "identity_provider": self.identity_provider,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "updated_at": self.updated_at.isoformat(),
            "waitlist_notified_at": self.waitlist_notified_at.isoformat()
            if self.waitlist_notified_at
            else None,
        }


class WorkspaceRole(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    MEMBER = "member", "Member"


class WorkspacePlan(models.TextChoices):
    TRIAL = "trial", "Trial"
    PRO = "pro", "Pro"
    ENTERPRISE = "enterprise", "Enterprise"
    SELF_HOSTED = "self_hosted", "Self-hosted"


class Workspace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uid = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workspaces_created",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    plan = models.CharField(
        max_length=32,
        choices=WorkspacePlan.choices,
        default=WorkspacePlan.TRIAL,
    )
    quota_overrides = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - admin helper
        return f"{self.name} ({self.uid})"

    @staticmethod
    def _unique_uid() -> str:
        """Generate a short, opaque UID and retry on rare collisions."""
        candidate = uuid.uuid4().hex[:12]
        while Workspace.objects.filter(uid=candidate).exists():
            candidate = uuid.uuid4().hex[:12]
        return candidate

    @classmethod
    def ensure_default_for_user(cls, user):
        if not user or not getattr(user, "pk", None):
            return None
        existing = (
            cls.objects.filter(members__user=user)
            .select_related("created_by")
            .order_by("created_at")
            .first()
        )
        if existing:
            return existing
        uid = cls._unique_uid()
        workspace = cls.objects.create(
            uid=uid,
            name="Personal",
            created_by=user,
        )
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=user,
            role=WorkspaceRole.OWNER,
        )
        return workspace

    @classmethod
    def create_for_user(cls, *, name: str, user) -> "Workspace":
        if not user or not getattr(user, "pk", None):
            raise PermissionError("Authentication required to create a workspace.")
        workspace_name = name or "Personal"
        uid = cls._unique_uid()
        workspace = cls.objects.create(uid=uid, name=workspace_name, created_by=user)
        WorkspaceMember.objects.create(
            workspace=workspace, user=user, role=WorkspaceRole.OWNER
        )
        return workspace

    @classmethod
    def resolve_for_user(cls, user, preferred_uid: str | None = None) -> "Workspace":
        queryset = cls.objects.filter(members__user=user).distinct()
        if preferred_uid and preferred_uid not in ("tenant-default", ""):
            match = queryset.filter(uid=preferred_uid).first()
            if match:
                return match
            raise PermissionError("You are not a member of the requested workspace.")
        existing = queryset.first()
        if existing:
            return existing
        resolved = cls.ensure_default_for_user(user)
        if resolved is None:
            raise PermissionError("Workspace membership required.")
        return resolved

    @classmethod
    def allowed_uids_for_user(cls, user) -> set[str]:
        if not user or not getattr(user, "pk", None):
            return set()
        existing = set(
            cls.objects.filter(members__user=user).values_list("uid", flat=True)
        )
        if existing:
            return existing
        workspace = cls.ensure_default_for_user(user)
        return {workspace.uid} if workspace else set()


class WorkspaceMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    role = models.CharField(
        max_length=32, choices=WorkspaceRole.choices, default=WorkspaceRole.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("workspace", "user")
        ordering = ["-joined_at"]

    def __str__(self) -> str:  # pragma: no cover - admin helper
        return f"{self.user} in {self.workspace} ({self.role})"
