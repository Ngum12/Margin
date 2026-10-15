"""Phase 5: export table; job types export_pdfs and export_dataset.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15 10:14:05.126902
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_JOB_TYPES = ("process_upload", "transcribe_script", "mark_script", "transcribe_page")
NEW_JOB_TYPES = (*OLD_JOB_TYPES, "export_pdfs", "export_dataset")


def _job_type_check(values: tuple[str, ...]) -> str:
    return "type IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _set_job_types(values: tuple[str, ...]) -> None:
    # Autogenerate does not see new values of a non-native enum; replace its CHECK by hand.
    with op.batch_alter_table("job", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_job_job_type"), type_="check")
        batch_op.create_check_constraint("job_type", _job_type_check(values))


def upgrade() -> None:
    _set_job_types(NEW_JOB_TYPES)
    op.create_table(
        "export",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "csv",
                "student_pdf",
                "class_pdf",
                "dataset",
                name="export_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("exam_id", sa.Integer(), nullable=True),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "done",
                "failed",
                name="export_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("filename", sa.String(length=200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("finished_at", app.db.base.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name=op.f("fk_export_exam_id_exam")),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["user.id"], name=op.f("fk_export_requested_by_id_user")
        ),
        sa.ForeignKeyConstraint(
            ["school_id"], ["school.id"], name=op.f("fk_export_school_id_school")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export")),
    )
    with op.batch_alter_table("export", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_export_exam_id"), ["exam_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_export_school_id"), ["school_id"], unique=False)


def downgrade() -> None:
    op.execute("DELETE FROM job WHERE type IN ('export_pdfs', 'export_dataset')")
    _set_job_types(OLD_JOB_TYPES)
    with op.batch_alter_table("export", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_export_school_id"))
        batch_op.drop_index(batch_op.f("ix_export_exam_id"))

    op.drop_table("export")
