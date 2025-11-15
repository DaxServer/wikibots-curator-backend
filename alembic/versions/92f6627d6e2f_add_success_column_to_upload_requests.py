"""add success column to upload_requests

Revision ID: 92f6627d6e2f
Revises: 867257161463
Create Date: 2025-11-15 12:37:52.280707

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "92f6627d6e2f"
down_revision: Union[str, Sequence[str], None] = "867257161463"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("upload_requests")]
    if "success" not in cols:
        op.execute(
            sa.text("ALTER TABLE upload_requests ADD COLUMN success VARCHAR(2000)")
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("upload_requests")]
    if "success" in cols:
        op.execute(sa.text("ALTER TABLE upload_requests DROP COLUMN success"))
