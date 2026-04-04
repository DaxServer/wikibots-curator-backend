"""squashed migrations

Revision ID: 8b31e3fb791b
Revises:
Create Date: 2026-04-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b31e3fb791b"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create full schema from scratch."""
    op.create_table(
        "users",
        sa.Column(
            "userid",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "username",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("userid"),
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)

    op.create_table(
        "batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "userid",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "edit_group_id",
            sqlmodel.sql.sqltypes.AutoString(length=12),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["userid"], ["users.userid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batches_userid"), "batches", ["userid"], unique=False)
    op.create_index(
        op.f("ix_batches_created_at"), "batches", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_batches_updated_at"), "batches", ["updated_at"], unique=False
    )

    op.create_table(
        "upload_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batchid", sa.Integer(), nullable=False),
        sa.Column(
            "userid",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "status",
            sqlmodel.sql.sqltypes.AutoString(length=50),
            nullable=False,
        ),
        sa.Column(
            "key",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "handler",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "collection",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column(
            "filename",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("wikitext", sa.Text(), nullable=False),
        sa.Column(
            "copyright_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("success", sa.Text(), nullable=True),
        sa.Column(
            "last_edited_by",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column(
            "celery_task_id",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batchid"], ["batches.id"]),
        sa.ForeignKeyConstraint(
            ["last_edited_by"],
            ["users.userid"],
            name=op.f("fk_upload_requests_last_edited_by_users"),
        ),
        sa.ForeignKeyConstraint(["userid"], ["users.userid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_upload_requests_batchid"),
        "upload_requests",
        ["batchid"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_batchid_status_updated_at"),
        "upload_requests",
        ["batchid", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_created_at"),
        "upload_requests",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_filename"),
        "upload_requests",
        ["filename"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_handler"),
        "upload_requests",
        ["handler"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_key"), "upload_requests", ["key"], unique=False
    )
    op.create_index(
        op.f("ix_upload_requests_last_edited_by"),
        "upload_requests",
        ["last_edited_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_status"),
        "upload_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_updated_at"),
        "upload_requests",
        ["updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_upload_requests_userid"),
        "upload_requests",
        ["userid"],
        unique=False,
    )

    op.create_table(
        "presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "userid",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "handler",
            sqlmodel.sql.sqltypes.AutoString(length=50),
            nullable=False,
        ),
        sa.Column(
            "title",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column(
            "title_template",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=False,
        ),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column(
            "categories",
            sqlmodel.sql.sqltypes.AutoString(length=500),
            nullable=True,
        ),
        sa.Column("exclude_from_date_category", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["userid"], ["users.userid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_presets_handler"), "presets", ["handler"], unique=False)
    op.create_index(
        op.f("ix_presets_is_default"), "presets", ["is_default"], unique=False
    )
    op.create_index(op.f("ix_presets_userid"), "presets", ["userid"], unique=False)


def downgrade() -> None:
    pass
