"""update_duplicate_status

Revision ID: 4ab5dee85aad
Revises: ed3e8b47a240
Create Date: 2025-12-15 13:05:19.149044

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4ab5dee85aad"
down_revision: Union[str, Sequence[str], None] = "ed3e8b47a240"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        sa.text(
            """
            UPDATE upload_requests SET status = 'duplicate'
            WHERE status = 'failed'
                AND JSON_UNQUOTE(JSON_EXTRACT(error, '$.type')) = 'duplicate'
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "UPDATE upload_requests SET status = 'failed' WHERE status = 'duplicate'"
        )
    )
