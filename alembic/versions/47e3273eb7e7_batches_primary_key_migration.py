"""batches primary key migration

Revision ID: 47e3273eb7e7
Revises: 079f0a6f0aed
Create Date: 2025-11-27 20:47:39.298575

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "47e3273eb7e7"
down_revision: Union[str, Sequence[str], None] = "079f0a6f0aed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("batches") as batch_op:
        # Make batch_uid non-nullable (it was PK)
        batch_op.alter_column(
            "batch_uid", existing_type=sa.String(length=255), nullable=False
        )

        # Make id non-nullable and auto-increment
        batch_op.alter_column(
            "id", existing_type=sa.Integer(), nullable=False, autoincrement=True
        )

        # Create new Primary Key on 'id'
        batch_op.create_primary_key("pk_batches", ["id"])

        # Create Unique Index on 'batch_uid'
        batch_op.create_index("ix_batches_batch_uid", ["batch_uid"], unique=True)

    # 6. Modify 'upload_requests' table: Add new FK

    with op.batch_alter_table("upload_requests") as batch_op:
        # Add new FK
        batch_op.create_foreign_key(
            "fk_upload_requests_batchid_batches", "batches", ["batchid"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    pass
