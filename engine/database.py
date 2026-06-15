import os
import time
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/workflow_engine")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class WorkflowRun(Base):
    __tablename__ = "runs"

    id            = Column(Integer, primary_key=True, index=True)
    goal          = Column(String)
    request       = Column(Text)
    status        = Column(String, default="success")
    steps         = Column(Integer)
    summary       = Column(Text, nullable=True)
    total_tokens  = Column(Integer, nullable=True)
    total_time_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


def init_db():
    retries = 5
    for attempt in range(retries):
        try:
            Base.metadata.create_all(bind=engine)
            print("✓ Database connected and tables created")
            return
        except Exception as e:
            if attempt < retries - 1:
                print(f"  DB not ready, retrying in 3s... (attempt {attempt + 1}/{retries})")
                time.sleep(3)
            else:
                raise e