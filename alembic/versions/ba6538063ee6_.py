"""empty message

Revision ID: ba6538063ee6
Revises: 867257161463
Create Date: 2025-11-28 11:18:16.381825

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ba6538063ee6"
down_revision: Union[str, Sequence[str], None] = "867257161463"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns("upload_requests")

    for column in columns:
        if column["name"] in ["wikitext", "sdc", "result", "error", "success"]:
            op.alter_column(
                "upload_requests",
                column["name"],
                existing_type=column["type"],
                type_=sa.Text(),
                existing_nullable=column["nullable"],
            )


def downgrade() -> None:
    """Downgrade schema."""
    pass
