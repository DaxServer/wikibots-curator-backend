"""remove sdc column from upload requests

Revision ID: 324d2fe7d7ec
Revises: b6b446c58114
Create Date: 2026-02-21 19:43:18.498307

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "324d2fe7d7ec"
down_revision: Union[str, Sequence[str], None] = "b6b446c58114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("uploadrequest", "sdc")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("uploadrequest", sa.Column("sdc", sa.JSON, nullable=True))
