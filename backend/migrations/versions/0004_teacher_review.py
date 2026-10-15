"""Phase 4: orientation layers, legacy covers, comments, review sessions, teacher decisions.

Legacy covers: Phase 2 stored cover images already turned upright and recorded the angle in
``rotation_applied``. That angle moves to ``rotation_baked`` (already applied to the image file,
never applied again); ``rotation_stack`` stays 0 for those pages.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15 05:27:43.604154
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_JOB_TYPES = ("process_upload", "transcribe_script", "mark_script")
NEW_JOB_TYPES = (*OLD_JOB_TYPES, "transcribe_page")


def _job_type_check(values: tuple[str, ...]) -> str:
    return "type IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # Autogenerate does not see new values of a non-native enum; replace its CHECK by hand.
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_job_job_type"), type_="check")
        batch_op.create_check_constraint("job_type", _job_type_check(NEW_JOB_TYPES))

    op.create_table(
        "question_comment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["question.id"], name=op.f("fk_question_comment_question_id_question")
        ),
        sa.ForeignKeyConstraint(
            ["script_id"], ["script.id"], name=op.f("fk_question_comment_script_id_script")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["user.id"], name=op.f("fk_question_comment_updated_by_id_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_comment")),
        sa.UniqueConstraint(
            "script_id", "question_id", name=op.f("uq_question_comment_script_id_question_id")
        ),
    )
    with op.batch_alter_table("question_comment", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_question_comment_script_id"), ["script_id"], unique=False
        )

    op.create_table(
        "review_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("opened_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("confirmed_at", app.db.base.UTCDateTime(), nullable=True),
        sa.Column("active_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_heartbeat_at", app.db.base.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["script_id"], ["script.id"], name=op.f("fk_review_session_script_id_script")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_review_session_user_id_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_session")),
    )
    with op.batch_alter_table("review_session", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_review_session_script_id"), ["script_id"], unique=False
        )

    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.alter_column("proposed_half_marks", existing_type=sa.INTEGER(), nullable=True)
        batch_op.alter_column("confidence", existing_type=sa.FLOAT(), nullable=True)
        batch_op.alter_column("error_category", existing_type=sa.VARCHAR(length=32), nullable=True)
        batch_op.alter_column("model_name", existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.alter_column("model_version", existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.alter_column("prompt_version", existing_type=sa.VARCHAR(length=100), nullable=True)
        batch_op.alter_column("proposed_at", existing_type=sa.DATETIME(), nullable=True)

    with op.batch_alter_table("page", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("rotation_baked", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("rotation_stack", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("rotation_auto", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("auto_rotation_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("auto_rotation_model", sa.String(length=100), nullable=True))
        batch_op.add_column(
            sa.Column("auto_rotation_prompt_version", sa.String(length=100), nullable=True)
        )
        batch_op.add_column(sa.Column("rotation_teacher", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "rotated_after_transcription",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    op.execute("UPDATE page SET rotation_baked = rotation_applied")
    with op.batch_alter_table("page", schema=None) as batch_op:
        batch_op.drop_column("rotation_applied")

    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reviewed_at", app.db.base.UTCDateTime(), nullable=True))

    with op.batch_alter_table("transcription", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rotation", sa.Integer(), nullable=False, server_default="0"))
        batch_op.drop_constraint(
            batch_op.f("uq_transcription_page_id_source_model_name_model_version_prompt_version"),
            type_="unique",
        )
        batch_op.create_unique_constraint(
            batch_op.f(
                "uq_transcription_page_id_source_model_name_model_version_prompt_version_rotation"
            ),
            ["page_id", "source", "model_name", "model_version", "prompt_version", "rotation"],
        )


def downgrade() -> None:
    op.execute("DELETE FROM job WHERE type = 'transcribe_page'")
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_job_job_type"), type_="check")
        batch_op.create_check_constraint("job_type", _job_type_check(OLD_JOB_TYPES))

    with op.batch_alter_table("transcription", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f(
                "uq_transcription_page_id_source_model_name_model_version_prompt_version_rotation"
            ),
            type_="unique",
        )
        batch_op.create_unique_constraint(
            batch_op.f("uq_transcription_page_id_source_model_name_model_version_prompt_version"),
            ["page_id", "source", "model_name", "model_version", "prompt_version"],
        )
        batch_op.drop_column("rotation")

    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.drop_column("reviewed_at")

    with op.batch_alter_table("page", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("rotation_applied", sa.INTEGER(), nullable=False, server_default="0")
        )
    op.execute("UPDATE page SET rotation_applied = rotation_baked")
    with op.batch_alter_table("page", schema=None) as batch_op:
        batch_op.drop_column("rotated_after_transcription")
        batch_op.drop_column("rotation_teacher")
        batch_op.drop_column("auto_rotation_prompt_version")
        batch_op.drop_column("auto_rotation_model")
        batch_op.drop_column("auto_rotation_confidence")
        batch_op.drop_column("rotation_auto")
        batch_op.drop_column("rotation_stack")
        batch_op.drop_column("rotation_baked")

    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.alter_column("proposed_at", existing_type=sa.DATETIME(), nullable=False)
        batch_op.alter_column(
            "prompt_version", existing_type=sa.VARCHAR(length=100), nullable=False
        )
        batch_op.alter_column("model_version", existing_type=sa.VARCHAR(length=100), nullable=False)
        batch_op.alter_column("model_name", existing_type=sa.VARCHAR(length=100), nullable=False)
        batch_op.alter_column("error_category", existing_type=sa.VARCHAR(length=32), nullable=False)
        batch_op.alter_column("confidence", existing_type=sa.FLOAT(), nullable=False)
        batch_op.alter_column("proposed_half_marks", existing_type=sa.INTEGER(), nullable=False)

    with op.batch_alter_table("review_session", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_review_session_script_id"))

    op.drop_table("review_session")
    with op.batch_alter_table("question_comment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_question_comment_script_id"))

    op.drop_table("question_comment")
