"""Page check before AI marking; live AI progress (script steps, model call timings).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15 16:12:04.928144
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.db.base

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_call",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "reader",
                "marker",
                name="model_call_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("seconds", sa.Float(), nullable=False),
        sa.Column("created_at", app.db.base.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_call")),
    )
    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_model_call_created_at"), ["created_at"], unique=False)

    with op.batch_alter_table("exam", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pages_checked_at", app.db.base.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column("pages_checked_by_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_exam_pages_checked_by_id_user"), "user", ["pages_checked_by_id"], ["id"]
        )

    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_step", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("ai_step_index", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ai_step_total", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ai_step_page_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("ai_step_started_at", app.db.base.UTCDateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.drop_column("ai_step_started_at")
        batch_op.drop_column("ai_step_page_id")
        batch_op.drop_column("ai_step_total")
        batch_op.drop_column("ai_step_index")
        batch_op.drop_column("ai_step")

    with op.batch_alter_table("exam", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_exam_pages_checked_by_id_user"), type_="foreignkey")
        batch_op.drop_column("pages_checked_by_id")
        batch_op.drop_column("pages_checked_at")

    with op.batch_alter_table("model_call", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_model_call_created_at"))

    op.drop_table("model_call")
