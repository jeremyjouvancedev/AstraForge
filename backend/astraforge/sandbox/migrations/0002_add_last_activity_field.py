from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("sandbox", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE sandbox_sandboxsession
            ADD COLUMN IF NOT EXISTS last_activity_at timestamp with time zone NULL;
            """,
            reverse_sql="""
            ALTER TABLE sandbox_sandboxsession
            DROP COLUMN IF EXISTS last_activity_at;
            """,
        ),
    ]

