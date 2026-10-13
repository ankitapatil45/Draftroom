"""Database tables and engine for session state, versions, and activity traces."""
import os
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Float,
    Integer,
    Index,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from .config import settings

metadata = MetaData()
EXPECTED_SCHEMA_VERSION = "0001_initial"
json_data = JSON().with_variant(JSONB(), "postgresql")

sessions = Table(
    "sessions",
    metadata,
    Column("id", String(12), primary_key=True),
    Column("created", Float, nullable=False),
    Column("data", json_data, nullable=False),
)
versions = Table(
    "versions",
    metadata,
    Column("session_id", String(12), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Column("number", Integer, primary_key=True),
    Column("state", json_data),
)
traces = Table(
    "traces",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(12), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("record", json_data, nullable=False),
)
Index("ix_traces_session_id", traces.c.session_id)

if settings.database_url.startswith("sqlite:"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)

if os.getenv("DRAFTROOM_MIGRATING") != "1":
    if settings.app_env != "production":
        metadata.create_all(engine)
    else:
        required_tables = {"alembic_version", "sessions", "versions", "traces"}
        missing_tables = required_tables - set(inspect(engine).get_table_names())
        if missing_tables:
            raise RuntimeError("Database schema is missing. Run `alembic upgrade head` before starting Draftroom.")
        with engine.connect() as connection:
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if version != EXPECTED_SCHEMA_VERSION:
            raise RuntimeError("Database schema is out of date. Run `alembic upgrade head` before starting Draftroom.")
