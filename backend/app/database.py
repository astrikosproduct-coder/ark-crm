import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

engine = create_engine(
    DATABASE_URL,
    # Off unless asked for. Echo logs every statement WITH its values — client
    # names, emails, deal figures — into the server log, and slows every
    # request. Set SQL_ECHO=true in .env to watch the SQL while debugging.
    echo=os.getenv("SQL_ECHO", "").lower() == "true",
    # Test a pooled connection before handing it out, so a database restart
    # costs one reconnect instead of a failed request per stale connection.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()