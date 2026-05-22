"""Database session helpers."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

_DEFAULT_DB = Path(__file__).resolve().parents[3] / "data" / "black_ink_signal.db"


def get_engine(db_path: str | None = None):
    path = db_path or str(_DEFAULT_DB)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session_factory(engine=None) -> sessionmaker[Session]:
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)
