"""initial schema: users, sessions, rooms, room_members

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("login", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("has_plus", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("token_enc", sa.Text),
        sa.Column("refresh_token_enc", sa.Text),
        sa.Column("token_expires_at", TS),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("provider", "external_id", name="uq_users_provider_ext"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("last_seen_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("slug", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column(
            "owner_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("state", sa.JSON, nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_rooms_owner_id", "rooms", ["owner_id"])
    op.create_table(
        "room_members",
        sa.Column(
            "room_id",
            sa.String(32),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("last_joined_at", TS, nullable=False),
        sa.Column("banned", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_room_members_user_id", "room_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("room_members")
    op.drop_table("rooms")
    op.drop_table("sessions")
    op.drop_table("users")
