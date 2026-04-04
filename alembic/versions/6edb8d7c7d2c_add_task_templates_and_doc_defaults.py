"""add task templates and doc defaults

Revision ID: 6edb8d7c7d2c
Revises: 0dbce9a0ed64
Create Date: 2026-04-01 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6edb8d7c7d2c"
down_revision: Union[str, Sequence[str], None] = "0dbce9a0ed64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("default_task_action", sa.Text(), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("default_task_instruction", sa.Text(), nullable=True)
    )
    op.execute(
        "UPDATE documents SET default_task_action = 'rewrite' WHERE default_task_action IS NULL"
    )
    op.create_table(
        "task_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("task_templates")
    op.drop_column("documents", "default_task_instruction")
    op.drop_column("documents", "default_task_action")
