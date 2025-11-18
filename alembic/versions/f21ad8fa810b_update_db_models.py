"""update db models

Revision ID: f21ad8fa810b
Revises: 92f6627d6e2f
Create Date: 2025-11-18 09:58:30.227916

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f21ad8fa810b"
down_revision: Union[str, Sequence[str], None] = "92f6627d6e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("upload_requests")]
    if "labels" not in cols:
        op.add_column("upload_requests", sa.Column("labels", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("upload_requests", "labels")
