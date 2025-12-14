"""initial schema

Revision ID: 867257161463
Revises:
Create Date: 2025-10-07 21:19:13.750858

"""

from typing import Sequence, Union

from sqlmodel import SQLModel

from alembic import op
from curator.app.db import engine

# revision identifiers, used by Alembic.
revision: str = "867257161463"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Downgrade schema."""
    pass
