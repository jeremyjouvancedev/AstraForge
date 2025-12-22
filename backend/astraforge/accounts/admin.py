from __future__ import annotations

from django.contrib import admin

from .models import ApiKey, UserAccess, Workspace, WorkspaceMember


@admin.register(UserAccess)
class UserAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "identity_provider", "approved_at", "updated_at")
    list_filter = ("status", "identity_provider")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "is_active", "created_at", "last_used_at")
    search_fields = ("name", "user__username")


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "uid", "created_by", "created_at")
    search_fields = ("name", "uid", "created_by__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ("workspace", "user", "role", "joined_at")
    list_filter = ("role",)
    search_fields = ("workspace__name", "workspace__uid", "user__username", "user__email")
    readonly_fields = ("joined_at",)
