import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Session

DATA_DIR = os.getenv("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "comments.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class ProcessedComment(Base):
    __tablename__ = "processed_comments"

    comment_id = Column(Text, primary_key=True)
    post_id = Column(Text, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow)
    action = Column(Text, nullable=False)  # "replied" | "skipped" | "random_skip"


def init_db() -> None:
    Base.metadata.create_all(engine)


def is_processed(comment_id: str) -> bool:
    with Session(engine) as session:
        return session.get(ProcessedComment, comment_id) is not None


def mark_processed(comment_id: str, post_id: str, action: str) -> None:
    with Session(engine) as session:
        record = ProcessedComment(
            comment_id=comment_id,
            post_id=post_id,
            processed_at=datetime.utcnow(),
            action=action,
        )
        session.merge(record)
        session.commit()
