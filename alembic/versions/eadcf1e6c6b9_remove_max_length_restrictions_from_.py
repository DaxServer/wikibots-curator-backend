"""Remove max_length restrictions from wikitext, sdc, error, and success fields

Revision ID: eadcf1e6c6b9
Revises: f21ad8fa810b
Create Date: 2025-11-23 14:31:15.961027

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "eadcf1e6c6b9"
down_revision: Union[str, Sequence[str], None] = "f21ad8fa810b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove max_length restrictions from text fields
    with op.batch_alter_table("upload_requests", schema=None) as batch_op:
        batch_op.alter_column(
            "wikitext",
            existing_type=sa.VARCHAR(length=2000),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "sdc",
            existing_type=sa.VARCHAR(length=2000),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "error",
            existing_type=sa.VARCHAR(length=2000),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "success",
            existing_type=sa.VARCHAR(length=2000),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Restore max_length restrictions to text fields
    with op.batch_alter_table("upload_requests", schema=None) as batch_op:
        batch_op.alter_column(
            "success",
            existing_type=sa.Text(),
            type_=sa.VARCHAR(length=2000),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "error",
            existing_type=sa.Text(),
            type_=sa.VARCHAR(length=2000),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "sdc",
            existing_type=sa.Text(),
            type_=sa.VARCHAR(length=2000),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "wikitext",
            existing_type=sa.Text(),
            type_=sa.VARCHAR(length=2000),
            existing_nullable=True,
        )
