import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/workflow_engine")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class WorkflowRun(Base):
    __tablename__ = "runs"

    id         = Column(Integer, primary_key=True, index=True)
    goal       = Column(String)
    request    = Column(Text)
    status     = Column(String, default="success")
    steps      = Column(Integer)
    summary    = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)