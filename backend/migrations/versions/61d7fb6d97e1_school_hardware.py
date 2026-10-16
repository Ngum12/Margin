"""school_hardware

Revision ID: 61d7fb6d97e1
Revises: 0009
Create Date: 2026-10-16 15:00:31.181025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "61d7fb6d97e1"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("upload") as batch:
        batch.alter_column("uploaded_by_id", existing_type=sa.Integer(), nullable=True)
    op.create_table(
        "exam_absence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exam.id"), nullable=False),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("student.id"), nullable=False),
        sa.Column("recorded_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.UniqueConstraint("exam_id", "student_id"),
    )

    op.create_table(
        "hardware",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("inbox_enabled", sa.Boolean(), nullable=False),
        sa.Column("printer_uri", sa.String(length=500), nullable=False),
        sa.Column("duplex", sa.Boolean(), nullable=False),
        sa.Column("last_scan_at", app.db.base.UTCDateTime(), nullable=True),
        sa.Column("test_started_at", app.db.base.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["school_id"], ["school.id"], name=op.f("fk_hardware_school_id_school")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hardware")),
        sa.UniqueConstraint("school_id", name=op.f("uq_hardware_school_id")),
    )
    op.create_table(
        "scan_batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["school_id"], ["school.id"], name=op.f("fk_scan_batch_school_id_school")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_batch")),
        sa.UniqueConstraint("school_id", "sha256", name=op.f("uq_scan_batch_school_id_sha256")),
    )
    with op.batch_alter_table("scan_batch", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_scan_batch_school_id"), ["school_id"], unique=False)

    op.create_table(
        "print_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=True),
        sa.Column("request_key", sa.String(length=100), nullable=False),
        sa.Column("script_ids", sa.JSON(), nullable=False),
        sa.Column("confirmation_versions", sa.JSON(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("printer_uri", sa.String(length=500), nullable=False),
        sa.Column("duplex", sa.Boolean(), nullable=False),
        sa.Column("printer_job_id", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name=op.f("fk_print_job_exam_id_exam")),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["user.id"], name=op.f("fk_print_job_requested_by_id_user")
        ),
        sa.ForeignKeyConstraint(
            ["school_id"], ["school.id"], name=op.f("fk_print_job_school_id_school")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_print_job")),
        sa.UniqueConstraint("request_key", name=op.f("uq_print_job_request_key")),
    )
    with op.batch_alter_table("print_job", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_print_job_school_id"), ["school_id"], unique=False)

    op.create_table(
        "intake_page",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("source_index", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("thumb_path", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("rotation", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("exam_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("discarded", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["scan_batch.id"], name=op.f("fk_intake_page_batch_id_scan_batch")
        ),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name=op.f("fk_intake_page_exam_id_exam")),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"], name=op.f("fk_intake_page_page_id_page")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intake_page")),
        sa.UniqueConstraint(
            "batch_id", "source_index", name=op.f("uq_intake_page_batch_id_source_index")
        ),
    )
    with op.batch_alter_table("intake_page", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_intake_page_batch_id"), ["batch_id"], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_table("exam_absence")
    # Automated uploads have no staff uploader; preserve them on downgrade.
    # SQLite permits the old application to read nullable uploader values.
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("intake_page", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_intake_page_batch_id"))

    op.drop_table("intake_page")
    with op.batch_alter_table("print_job", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_print_job_school_id"))

    op.drop_table("print_job")
    with op.batch_alter_table("scan_batch", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_scan_batch_school_id"))

    op.drop_table("scan_batch")
    op.drop_table("hardware")
    # ### end Alembic commands ###
