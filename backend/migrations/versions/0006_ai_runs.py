"""Re-run AI marking: run numbers on scripts and mark decisions (existing rows are run 0).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15 11:14:01.732019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_run", sa.Integer(), nullable=False, server_default="0"))
        batch_op.drop_constraint(
            batch_op.f(
                "uq_mark_decision_script_id_mark_scheme_point_id_model_name_model_version_prompt_version"
            ),
            type_="unique",
        )
        batch_op.create_unique_constraint(
            batch_op.f(
                "uq_mark_decision_script_id_mark_scheme_point_id_model_name_model_version_prompt_version_ai_run"
            ),
            [
                "script_id",
                "mark_scheme_point_id",
                "model_name",
                "model_version",
                "prompt_version",
                "ai_run",
            ],
        )

    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_run", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    # The old uniqueness rule allows one run per model and prompt: keep each script's current run.
    op.execute(
        "DELETE FROM mark_decision WHERE ai_run <> "
        "(SELECT script.ai_run FROM script WHERE script.id = mark_decision.script_id)"
    )
    with op.batch_alter_table("script", schema=None) as batch_op:
        batch_op.drop_column("ai_run")

    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f(
                "uq_mark_decision_script_id_mark_scheme_point_id_model_name_model_version_prompt_version_ai_run"
            ),
            type_="unique",
        )
        batch_op.create_unique_constraint(
            batch_op.f(
                "uq_mark_decision_script_id_mark_scheme_point_id_model_name_model_version_prompt_version"
            ),
            ["script_id", "mark_scheme_point_id", "model_name", "model_version", "prompt_version"],
        )
        batch_op.drop_column("ai_run")
