from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class RepositoryLink(models.Model):
    class Provider(models.TextChoices):
        GITLAB = "gitlab", "GitLab"
        GITHUB = "github", "GitHub"

    DEFAULT_GITLAB_URL = "https://gitlab.com"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="repository_links",
    )
    provider = models.CharField(max_length=20, choices=Provider.choices)
    repository = models.CharField(max_length=255)
    access_token = models.TextField()
    base_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Repository Link"
        verbose_name_plural = "Repository Links"
        unique_together = ("user", "provider", "repository")
        ordering = ["created_at"]

    def token_preview(self) -> str:
        suffix = self.access_token[-4:] if self.access_token else ""
        return f"***{suffix}" if suffix else ""

    def effective_base_url(self) -> str | None:
        if self.provider == self.Provider.GITLAB:
            return self.base_url or self.DEFAULT_GITLAB_URL
        return self.base_url or None
