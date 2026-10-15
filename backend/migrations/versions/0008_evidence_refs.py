"""Where each proposal's evidence is on the page (for the red pen).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15 18:03:28.169084
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.add_column(sa.Column("evidence_refs", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mark_decision", schema=None) as batch_op:
        batch_op.drop_column("evidence_refs")
