"""add checkout requests

Revision ID: a6b7c8d9e0f1
Revises: 9f2a6c7d8e9f
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a6b7c8d9e0f1"
down_revision = "9f2a6c7d8e9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkout_requests",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hostel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hostel_id"], ["hostels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_id", name="uq_checkout_request_booking"),
    )
    op.create_index("ix_checkout_requests_booking_id", "checkout_requests", ["booking_id"])
    op.create_index("ix_checkout_requests_hostel_id", "checkout_requests", ["hostel_id"])
    op.create_index("ix_checkout_requests_requested_by", "checkout_requests", ["requested_by"])
    op.create_index("ix_checkout_requests_status", "checkout_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_checkout_requests_status", table_name="checkout_requests")
    op.drop_index("ix_checkout_requests_requested_by", table_name="checkout_requests")
    op.drop_index("ix_checkout_requests_hostel_id", table_name="checkout_requests")
    op.drop_index("ix_checkout_requests_booking_id", table_name="checkout_requests")
    op.drop_table("checkout_requests")
