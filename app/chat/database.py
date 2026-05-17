"""
database.py — SQLAlchemy engine + session factory.
Uses SQLite locally, easily swappable to PostgreSQL for production.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DBSession

from app.core.config import config
from app.chat.models import Base


# SQLite for local dev — change DB_URL in config for PostgreSQL in production
engine = create_engine(
    config.DB_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
    echo=False,   # set True to see raw SQL queries during debugging
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    print(f"✓ Database ready at: {config.DB_URL}")


def get_db():
    """
    FastAPI dependency — yields a DB session and closes it after the request.

    Usage in a route:
        @router.post("/chat")
        def chat(db: DBSession = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()