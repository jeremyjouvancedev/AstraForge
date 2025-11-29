from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("sandbox", "0002_add_last_activity_field"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS sandbox_sandboxsnapshot (
                id uuid PRIMARY KEY,
                label varchar(255) NOT NULL DEFAULT '',
                s3_key varchar(512) NOT NULL DEFAULT '',
                archive_path varchar(512) NOT NULL DEFAULT '',
                size_bytes bigint NOT NULL DEFAULT 0,
                include_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
                exclude_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
                created_at timestamp with time zone NOT NULL DEFAULT now(),
                session_id uuid NOT NULL
                    REFERENCES sandbox_sandboxsession(id)
                    DEFERRABLE INITIALLY DEFERRED
            );

            CREATE INDEX IF NOT EXISTS sandbox_snap_session_idx
                ON sandbox_sandboxsnapshot(session_id);

            CREATE TABLE IF NOT EXISTS sandbox_sandboxartifact (
                id uuid PRIMARY KEY,
                filename varchar(255) NOT NULL,
                content_type varchar(100) NOT NULL DEFAULT '',
                size_bytes bigint NOT NULL DEFAULT 0,
                storage_path varchar(512) NOT NULL,
                download_url varchar(512) NOT NULL DEFAULT '',
                created_at timestamp with time zone NOT NULL DEFAULT now(),
                session_id uuid NOT NULL
                    REFERENCES sandbox_sandboxsession(id)
                    DEFERRABLE INITIALLY DEFERRED
            );

            CREATE INDEX IF NOT EXISTS sandbox_art_session_idx
                ON sandbox_sandboxartifact(session_id);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS sandbox_snap_session_idx;
            DROP TABLE IF EXISTS sandbox_sandboxsnapshot;

            DROP INDEX IF EXISTS sandbox_art_session_idx;
            DROP TABLE IF EXISTS sandbox_sandboxartifact;
            """,
        ),
    ]

