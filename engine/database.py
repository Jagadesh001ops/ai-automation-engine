import os
import time
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

try:
    from pgvector.sqlalchemy import Vector as _Vector
    _VECTOR_DIMS = 384  # all-MiniLM-L6-v2 output size
    _VectorCol = lambda: Column(_Vector(_VECTOR_DIMS), nullable=True)  # noqa: E731
    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False
    _VectorCol = lambda: Column(Text, nullable=True)  # fallback: store as JSON text  # noqa: E731

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/workflow_engine")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Document(Base):
    """Uploaded source document (one row per upload after dedup)."""
    __tablename__ = "documents"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(String, nullable=True, index=True)   # auth user — null = pre-auth rows
    filename      = Column(String, nullable=False)
    content_type  = Column(String, nullable=False)
    size_bytes    = Column(Integer, nullable=False)
    page_count    = Column(Integer, nullable=True)
    char_count    = Column(Integer, nullable=True)
    content_hash  = Column(String(64), nullable=False, index=True)  # unique per user
    status        = Column(String, default="ready")   # processing | ready | failed
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


class DocumentChunk(Base):
    """One retrievable chunk extracted from a Document."""
    __tablename__ = "document_chunks"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer, primary_key=True, index=True)
    document_id   = Column(Integer, nullable=False, index=True)
    chunk_index   = Column(Integer, nullable=False)   # 0-based order within doc
    char_start    = Column(Integer, nullable=False)
    char_end      = Column(Integer, nullable=False)
    content_hash  = Column(String(64), nullable=False, index=True)
    text          = Column(Text, nullable=False)
    embedding     = _VectorCol()
    created_at    = Column(DateTime, default=datetime.utcnow)


class WorkflowRun(Base):
    __tablename__ = "runs"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(String, nullable=True, index=True)
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


class QuizAttempt(Base):
    """One user's answer to one quiz question (Day 13)."""
    __tablename__ = "quiz_attempts"
    __table_args__ = {"extend_existing": True}

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(String, nullable=False, index=True)
    run_id        = Column(Integer, nullable=True, index=True)   # workflow run that generated the quiz
    question_idx  = Column(Integer, nullable=False)              # 0-based index within quiz
    question_text = Column(Text, nullable=False)
    chosen_answer = Column(String(1), nullable=False)            # A/B/C/D
    correct_answer= Column(String(1), nullable=False)
    is_correct    = Column(Integer, nullable=False)              # 0/1 (SQLite-safe bool)
    created_at    = Column(DateTime, default=datetime.utcnow)


def _sync_columns():
    """Add any model columns missing from already-existing tables."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    models = [WorkflowRun, Document, DocumentChunk, QuizAttempt]
    with engine.begin() as conn:
        for model in models:
            tname = model.__tablename__
            if tname not in existing_tables:
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(tname)}
            for column in model.__table__.columns:
                if column.name not in existing_cols:
                    col_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {tname} ADD COLUMN "{column.name}" {col_type}'))


MAX_DOCS_PER_USER = 10


def get_or_create_document(db, *, filename: str, content_type: str,
                            size_bytes: int, page_count: int,
                            char_count: int, content_hash: str,
                            user_id: str = None) -> tuple:
    """Return (document, created: bool).

    Dedup by (user_id, content_hash) so the same file can be uploaded by
    different users without conflicting.  Enforces MAX_DOCS_PER_USER quota.
    """
    q = db.query(Document).filter_by(content_hash=content_hash)
    if user_id:
        q = q.filter_by(user_id=user_id)
    existing = q.first()
    if existing:
        return existing, False

    # Quota check
    if user_id:
        count = db.query(Document).filter_by(user_id=user_id).count()
        if count >= MAX_DOCS_PER_USER:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=429,
                detail=f"Document quota reached ({MAX_DOCS_PER_USER} documents per user). Delete a document to upload more.",
            )

    doc = Document(
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        page_count=page_count,
        char_count=char_count,
        content_hash=content_hash,
        status="ready",
    )
    db.add(doc)
    db.flush()
    return doc, True


def store_chunks(db, document_id: int, chunks, embeddings: list) -> int:
    """Insert DocumentChunk rows, skipping any that already exist (dedup).

    Returns the number of newly inserted chunks.
    """
    inserted = 0
    existing_hashes = {
        h for (h,) in
        db.query(DocumentChunk.content_hash)
          .filter_by(document_id=document_id)
          .all()
    }
    for chunk, embedding in zip(chunks, embeddings):
        if chunk.content_hash in existing_hashes:
            continue
        db.add(DocumentChunk(
            document_id=document_id,
            chunk_index=chunk.index,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            content_hash=chunk.content_hash,
            text=chunk.text,
            embedding=embedding,
        ))
        inserted += 1
    return inserted


def init_db():
    retries = 5
    for attempt in range(retries):
        try:
            try:
                with engine.begin() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                pass  # pgvector not installed on this Postgres — fall back to text embedding column
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
