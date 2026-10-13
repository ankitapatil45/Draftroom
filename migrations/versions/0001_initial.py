"""Create session, version, and trace tables."""
from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    bind = op.get_bind()
    existing = set() if context.is_offline_mode() else set(sa.inspect(bind).get_table_names())
    if "sessions" not in existing:
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(length=12), primary_key=True),
            sa.Column("created", sa.Float(), nullable=False),
            sa.Column("data", _json_type(), nullable=False),
        )
    if "versions" not in existing:
        op.create_table(
            "versions",
            sa.Column("session_id", sa.String(length=12), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("state", _json_type(), nullable=True),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("session_id", "number"),
        )
    if "traces" not in existing:
        op.create_table(
            "traces",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.String(length=12), nullable=False),
            sa.Column("record", _json_type(), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = set() if context.is_offline_mode() else {
        index["name"] for index in sa.inspect(bind).get_indexes("traces")
    }
    if "ix_traces_session_id" not in indexes:
        op.create_index("ix_traces_session_id", "traces", ["session_id"])


def downgrade():
    bind = op.get_bind()
    existing = {"sessions", "versions", "traces"} if context.is_offline_mode() else set(
        sa.inspect(bind).get_table_names()
    )
    if "traces" in existing:
        op.drop_table("traces")
    if "versions" in existing:
        op.drop_table("versions")
    if "sessions" in existing:
        op.drop_table("sessions")
