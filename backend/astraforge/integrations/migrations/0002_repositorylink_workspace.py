from __future__ import annotations

import uuid

from django.db import migrations, models
import django.db.models.deletion


def _unique_workspace_uid(workspace_model):
    candidate = uuid.uuid4().hex[:12]
    while workspace_model.objects.filter(uid=candidate).exists():
        candidate = uuid.uuid4().hex[:12]
    return candidate


def assign_workspaces(apps, schema_editor):
    RepositoryLink = apps.get_model("integrations", "RepositoryLink")
    Workspace = apps.get_model("accounts", "Workspace")
    WorkspaceMember = apps.get_model("accounts", "WorkspaceMember")

    for link in RepositoryLink.objects.select_related("user").all():
        user = link.user
        if user is None:
            continue
        workspace = (
            Workspace.objects.filter(members__user=user)
            .order_by("created_at")
            .first()
        )
        if workspace is None:
            uid = _unique_workspace_uid(Workspace)
            workspace = Workspace.objects.create(
                uid=uid,
                name="Personal",
                created_by=user,
            )
            WorkspaceMember.objects.create(
                workspace=workspace,
                user=user,
                role="owner",
            )
        link.workspace = workspace
        link.save(update_fields=["workspace"])


class Migration(migrations.Migration):
    # Avoid pending trigger events on Postgres when the data migration touches
    # accounts_workspace and we later alter constraints in the same migration.
    atomic = False

    dependencies = [
        ("accounts", "0005_workspace_and_members"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="repositorylink",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspace_repository_links",
                to="accounts.workspace",
            ),
        ),
        migrations.RunPython(assign_workspaces, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="repositorylink",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspace_repository_links",
                to="accounts.workspace",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="repositorylink",
            unique_together={("workspace", "provider", "repository")},
        ),
    ]
