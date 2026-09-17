import os
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
SessionLocal = sessionmaker(engine)
class Base(DeclarativeBase):
    pass
def now():
    return datetime.now(timezone.utc)
def db():
    with SessionLocal() as session:
        yield session
