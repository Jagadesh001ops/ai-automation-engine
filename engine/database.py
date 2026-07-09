import os
import time
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/workflow_engine")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class WorkflowRun(Base):
    __tablename__ = "runs"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer, primary_key=True, index=True)
    goal          = Column(String)
    request       = Column(Text)
    status        = Column(String, default="success")
    steps         = Column(Integer)
    steps_json    = Column(Text, nullable=True)
    summary       = Column(Text, nullable=True)
    output_json   = Column(Text, nullable=True)
    total_tokens  = Column(Integer, nullable=True)
    total_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


def _sync_columns():
    """Add any model columns missing from an already-existing table.

    create_all() only creates missing tables, it never alters existing
    ones — so columns added to WorkflowRun after the table was first
    created (e.g. steps_json, output_json) have to be patched in by hand.
    """
    inspector = inspect(engine)
    if "runs" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("runs")}
    with engine.begin() as conn:
        for column in WorkflowRun.__table__.columns:
            if column.name not in existing:
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE runs ADD COLUMN "{column.name}" {col_type}'))


def init_db():
    retries = 5
    for attempt in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            _sync_columns()
            print("OK - Database connected and tables created")
            return
        except Exception as e:
            if attempt < retries - 1:
                print(f"  DB not ready, retrying in 3s... (attempt {attempt + 1}/{retries})")
                time.sleep(3)
            else:
                raise e
