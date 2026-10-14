"""Phase 3: job table, worker heartbeat, transcriptions, mark decisions, model versions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 11:56:44.780292
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "process_upload",
                "transcribe_script",
                "mark_script",
                name="job_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                name="job_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("heartbeat_at", app.db.base.UTCDateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("started_at", app.db.base.UTCDateTime(), nullable=True),
        sa.Column("finished_at", app.db.base.UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_job_idempotency_key")),
    )
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_job_status"), ["status"], unique=False)

    op.create_table(
        "model_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "reader",
                "marker",
                name="model_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("installed_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_version")),
        sa.UniqueConstraint(
            "name", "version", "role", name=op.f("uq_model_version_name_version_role")
        ),
    )
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=False),
        sa.Column("started_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("seen_at", app.db.base.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_heartbeat")),
        sa.UniqueConstraint("worker_id", name=op.f("uq_worker_heartbeat_worker_id")),
    )
    op.create_table(
        "mark_decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("mark_scheme_point_id", sa.Integer(), nullable=False),
        sa.Column("proposed_half_marks", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "error_category",
            sa.Enum(
                "correct",
                "conceptual_error",
                "language_expression",
                "transcription_uncertain",
                "omitted",
                name="error_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("proposed_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("final_half_marks", sa.Integer(), nullable=True),
        sa.Column(
            "final_category",
            sa.Enum(
                "correct",
                "conceptual_error",
                "language_expression",
                "transcription_uncertain",
                "omitted",
                name="final_error_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", app.db.base.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["user.id"], name=op.f("fk_mark_decision_decided_by_id_user")
        ),
        sa.ForeignKeyConstraint(
            ["mark_scheme_point_id"],
            ["mark_scheme_point.id"],
            name=op.f("fk_mark_decision_mark_scheme_point_id_mark_scheme_point"),
        ),
        sa.ForeignKeyConstraint(
            ["script_id"], ["script.id"], name=op.f("fk_mark_decision_script_id_script")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mark_decision")),
        sa.UniqueConstraint(
            "script_id",
            "mark_scheme_point_id",
            "model_name",
            "model_version",
            "prompt_version",
            name=op.f(
                "uq_mark_decision_script_id_mark_scheme_point_id_model_name_model_version_prompt_version"
            ),
        ),
    )
    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mark_decision_script_id"), ["script_id"], unique=False)

    op.create_table(
        "transcription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "model",
                "teacher",
                name="transcription_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["user.id"], name=op.f("fk_transcription_created_by_id_user")
        ),
        sa.ForeignKeyConstraint(
            ["page_id"], ["page.id"], name=op.f("fk_transcription_page_id_page")
        ),
        sa.ForeignKeyConstraint(
            ["script_id"], ["script.id"], name=op.f("fk_transcription_script_id_script")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcription")),
        sa.UniqueConstraint(
            "page_id",
            "source",
            "model_name",
            "model_version",
            "prompt_version",
            name=op.f("uq_transcription_page_id_source_model_name_model_version_prompt_version"),
        ),
    )
    with op.batch_alter_table("transcription", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_transcription_page_id"), ["page_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_transcription_script_id"), ["script_id"], unique=False)

    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.add_column(sa.Column("manual_reason", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("ai_started_at", app.db.base.UTCDateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.drop_column("ai_started_at")
        batch_op.drop_column("manual_reason")

    with op.batch_alter_table("transcription", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_transcription_script_id"))
        batch_op.drop_index(batch_op.f("ix_transcription_page_id"))

    op.drop_table("transcription")
    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mark_decision_script_id"))

    op.drop_table("mark_decision")
    op.drop_table("worker_heartbeat")
    op.drop_table("model_version")
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_status"))

    op.drop_table("job")
