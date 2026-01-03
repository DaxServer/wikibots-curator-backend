"""Add sdc_v2 to upload_requests

Revision ID: 3f0f4e5a2b1c
Revises: 25ebee3eeed4
Create Date: 2026-01-03 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f0f4e5a2b1c"
down_revision: Union[str, Sequence[str], None] = "25ebee3eeed4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("upload_requests", sa.Column("sdc_v2", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("upload_requests", "sdc_v2")
