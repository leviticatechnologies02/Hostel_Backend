"""add extended room types

Revision ID: 9f2a6c7d8e9f
Revises: e547c1c574ce
Create Date: 2026-10-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9f2a6c7d8e9f"
down_revision: Union[str, Sequence[str], None] = "e547c1c574ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enum values supported by RoomType but missing from PostgreSQL."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE roomtype ADD VALUE IF NOT EXISTS 'QUADRUPLE'")
        op.execute("ALTER TYPE roomtype ADD VALUE IF NOT EXISTS 'FIVE_BED'")
        op.execute("ALTER TYPE roomtype ADD VALUE IF NOT EXISTS 'SIX_BED'")


def downgrade() -> None:
    """PostgreSQL enum values cannot be removed safely."""
    pass
