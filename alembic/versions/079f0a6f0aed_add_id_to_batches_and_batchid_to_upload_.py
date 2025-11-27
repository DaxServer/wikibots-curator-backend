"""add_id_to_batches_and_batchid_to_upload_requests

Revision ID: 079f0a6f0aed
Revises: eadcf1e6c6b9
Create Date: 2025-11-27 14:15:35.239268

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "079f0a6f0aed"
down_revision: Union[str, Sequence[str], None] = "eadcf1e6c6b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    session = sa.orm.Session(bind=bind)
    inspector = sa.inspect(bind)

    # 1. Add 'id' column to 'batches' (nullable initially)
    with op.batch_alter_table("batches") as batch_op:
        batch_op.add_column(
            sa.Column("id", sa.Integer(), nullable=True), if_not_exists=True
        )

    # 2. Populate 'batches.id'
    # We use a loop to ensure unique sequential IDs
    batches = session.execute(
        sa.text("SELECT batch_uid FROM batches ORDER BY created_at")
    ).fetchall()
    batch_uid_to_id = {}
    for i, (b_uid,) in enumerate(batches, start=1):
        session.execute(
            sa.text("UPDATE batches SET id = :id WHERE batch_uid = :uid"),
            {"id": i, "uid": b_uid},
        )
        batch_uid_to_id[b_uid] = i

    # 3. Add 'batchid' column to 'upload_requests' (nullable initially)
    with op.batch_alter_table("upload_requests") as batch_op:
        batch_op.add_column(
            sa.Column("batchid", sa.Integer(), nullable=True), if_not_exists=True
        )

    # 4. Populate 'upload_requests.batchid'
    # We can use a direct UPDATE with subquery which works in SQLite and MariaDB
    op.execute(
        """
        UPDATE upload_requests
        SET batchid = (SELECT id FROM batches WHERE batches.batch_uid = upload_requests.batch_id)
    """
    )

    op.create_index(table_name="batches", columns=["batch_uid"], unique=True)

    # 5. Modify 'batches' table: Make 'id' PK, 'batch_uid' Unique but not PK
    # We use recreate='always' to handle SQLite limitations and PK changes

    # Drop existing foreign key constraint from upload_requests referencing batches.batch_uid
    # Find the old FK name to drop it
    old_fk_name = None
    fks = inspector.get_foreign_keys("upload_requests")
    for fk in fks:
        if (
            fk["referred_table"] == "batches"
            and "batch_id" in fk["constrained_columns"]
        ):
            old_fk_name = fk["name"]
            break

    if old_fk_name:
        batch_op.drop_constraint(old_fk_name, type_="foreignkey")

    op.execute("ALTER TABLE batches MODIFY batch_uid VARCHAR(255) NOT NULL")
    op.execute("ALTER TABLE batches DROP PRIMARY KEY")

    op.alter_column(
        "batches",
        "id",
        existing_type=sa.Integer(),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Destructive migration
    pass
