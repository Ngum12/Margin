"""Phase 2: cover sheets, uploads, scripts and pages.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 10:12:46.093179
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cover_sheet",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name=op.f("fk_cover_sheet_exam_id_exam")),
        sa.ForeignKeyConstraint(
            ["student_id"], ["student.id"], name=op.f("fk_cover_sheet_student_id_student")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cover_sheet")),
        sa.UniqueConstraint(
            "exam_id", "student_id", name=op.f("uq_cover_sheet_exam_id_student_id")
        ),
        sa.UniqueConstraint("token", name=op.f("uq_cover_sheet_token")),
    )
    with op.batch_alter_table("cover_sheet", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cover_sheet_exam_id"), ["exam_id"], unique=False)

    op.create_table(
        "script",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "waiting",
                "transcribed",
                "ai_marked",
                "in_review",
                "confirmed",
                name="script_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", app.db.base.UTCDateTime(), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["confirmed_by_id"], ["user.id"], name=op.f("fk_script_confirmed_by_id_user")
        ),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name=op.f("fk_script_exam_id_exam")),
        sa.ForeignKeyConstraint(
            ["student_id"], ["student.id"], name=op.f("fk_script_student_id_student")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_script")),
        sa.UniqueConstraint("exam_id", "student_id", name=op.f("uq_script_exam_id_student_id")),
    )
    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_script_exam_id"), ["exam_id"], unique=False)

    op.create_table(
        "upload",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "processed",
                "failed",
                name="upload_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.Column("processed_at", app.db.base.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["exam_id"], ["exam.id"], name=op.f("fk_upload_exam_id_exam")),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"], ["user.id"], name=op.f("fk_upload_uploaded_by_id_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload")),
        sa.UniqueConstraint("exam_id", "sha256", name=op.f("uq_upload_exam_id_sha256")),
    )
    with op.batch_alter_table("upload", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_upload_exam_id"), ["exam_id"], unique=False)

    op.create_table(
        "page",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.Integer(), nullable=False),
        sa.Column("source_page_index", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("thumb_path", sa.String(length=500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("rotation_applied", sa.Integer(), nullable=False),
        sa.Column("is_cover", sa.Boolean(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "assigned",
                "unassigned",
                "discarded",
                name="page_state",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("script_id", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column(
            "unassigned_reason",
            sa.Enum(
                "before_first_cover",
                "follows_unassigned_cover",
                "qr_damaged",
                "qr_unreadable",
                "qr_conflict",
                "qr_not_ours",
                "qr_bad_checksum",
                "unknown_sheet",
                "other_exam",
                "duplicate_in_upload",
                "already_uploaded",
                "returned_by_teacher",
                name="unassigned_reason",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=True,
        ),
        sa.Column("related_page_id", sa.Integer(), nullable=True),
        sa.Column("detected_exam_id", sa.Integer(), nullable=True),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["detected_exam_id"], ["exam.id"], name=op.f("fk_page_detected_exam_id_exam")
        ),
        sa.ForeignKeyConstraint(
            ["related_page_id"], ["page.id"], name=op.f("fk_page_related_page_id_page")
        ),
        sa.ForeignKeyConstraint(
            ["script_id"], ["script.id"], name=op.f("fk_page_script_id_script")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["upload.id"], name=op.f("fk_page_upload_id_upload")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page")),
        sa.UniqueConstraint(
            "upload_id", "source_page_index", name=op.f("uq_page_upload_id_source_page_index")
        ),
    )
    with op.batch_alter_table("page", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_page_script_id"), ["script_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_page_upload_id"), ["upload_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("page", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_page_upload_id"))
        batch_op.drop_index(batch_op.f("ix_page_script_id"))

    op.drop_table("page")
    with op.batch_alter_table("upload", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_upload_exam_id"))

    op.drop_table("upload")
    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_script_exam_id"))

    op.drop_table("script")
    with op.batch_alter_table("cover_sheet", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cover_sheet_exam_id"))

    op.drop_table("cover_sheet")
