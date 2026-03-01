"""add unique constraint for default presets

Revision ID: 132e3ec448f0
Revises: 8b31e3fb791b
Create Date: 2026-02-22 14:34:03.748746

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "132e3ec448f0"
down_revision: Union[str, Sequence[str], None] = "8b31e3fb791b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_presets_unique_default",
        "presets",
        ["userid", "handler"],
        unique=True,
        postgresql_where=sa.text("is_default = TRUE"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_presets_unique_default", table_name="presets")
