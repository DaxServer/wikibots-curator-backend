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
        batch_op.add_column(sa.Column("id", sa.Integer(), nullable=True))

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
        batch_op.add_column(sa.Column("batchid", sa.Integer(), nullable=True))

    # 4. Populate 'upload_requests.batchid'
    # We can use a direct UPDATE with subquery which works in SQLite and MariaDB
    op.execute(
        """
        UPDATE upload_requests
        SET batchid = (SELECT id FROM batches WHERE batches.batch_uid = upload_requests.batch_id)
    """
    )

    # 5. Modify 'batches' table: Make 'id' PK, 'batch_uid' Unique but not PK
    # We use recreate='always' to handle SQLite limitations and PK changes
    with op.batch_alter_table("batches") as batch_op:
        # Make id non-nullable and auto-increment
        batch_op.alter_column(
            "id", existing_type=sa.Integer(), nullable=False, autoincrement=True
        )
        # Make batch_uid non-nullable (it was PK)
        batch_op.alter_column(
            "batch_uid", existing_type=sa.String(length=255), nullable=False
        )

        # Create new Primary Key on 'id'
        # Note: In batch mode, creating a new PK usually supersedes the old one if the table is recreated
        batch_op.create_primary_key("pk_batches", ["id"])

        # Create Unique Index on 'batch_uid'
        batch_op.create_index("ix_batches_batch_uid", ["batch_uid"], unique=True)

    # 6. Modify 'upload_requests' table: Drop old FK, Add new FK

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

    with op.batch_alter_table("upload_requests") as batch_op:
        if old_fk_name:
            batch_op.drop_constraint(old_fk_name, type_="foreignkey")

        # Add new FK
        batch_op.create_foreign_key(
            "fk_upload_requests_batchid_batches", "batches", ["batchid"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""

    # 1. Revert 'upload_requests'
    # Find new FK name
    new_fk_name = "fk_upload_requests_batchid_batches"
    # (or find dynamically if we want to be safe, but we named it explicitly)

    with op.batch_alter_table("upload_requests") as batch_op:
        batch_op.drop_constraint(new_fk_name, type_="foreignkey")
        # Re-add old FK (we assume batch_id column still exists)
        # We need to target batches.batch_uid.
        # Note: batch_uid must be unique (which it is).
        batch_op.create_foreign_key(
            "fk_upload_requests_batch_id_batches",
            "batches",
            ["batch_id"],
            ["batch_uid"],
        )

        batch_op.drop_column("batchid")

    # 2. Revert 'batches'
    with op.batch_alter_table("batches") as batch_op:
        batch_op.drop_index("ix_batches_batch_uid")
        # Drop PK on id
        # batch_op.drop_constraint('pk_batches', type_='primary') # Not needed if we recreate with new PK

        # Restore PK on batch_uid
        batch_op.create_primary_key("pk_batches_old", ["batch_uid"])

        batch_op.drop_column("id")
