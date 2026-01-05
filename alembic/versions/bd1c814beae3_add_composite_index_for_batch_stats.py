"""add_composite_index_for_batch_stats

Revision ID: bd1c814beae3
Revises: ee36be0a76c7
Create Date: 2026-01-05 15:45:20.864787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'bd1c814beae3'
down_revision: Union[str, Sequence[str], None] = 'ee36be0a76c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add composite index on (batchid, updated_at) for upload_requests
    # This significantly speeds up stats aggregation and change detection queries
    op.create_index(
        op.f("ix_upload_requests_batchid_status_updated_at"),
        "upload_requests",
        ["batchid", "status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop composite index
    op.drop_index(
        op.f("ix_upload_requests_batchid_status_updated_at"), table_name="upload_requests"
    )
