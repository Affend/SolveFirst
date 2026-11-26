"""Connection to TiDB Cloud through SQLAlchemy, using the same SSL setup as test_tidb.py."""

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# URL.create escapes special characters in the password for us.
database_url = URL.create(
    drivername="mysql+pymysql",
    username=settings.tidb_user,
    password=settings.tidb_password,
    host=settings.tidb_host,
    port=settings.tidb_port,
    database=settings.tidb_database,
    query={"charset": "utf8mb4"},  # full Unicode: math symbols, Indonesian text, emoji
)

engine = create_engine(
    database_url,
    # TiDB Cloud only accepts encrypted connections. Same as test_tidb.py.
    connect_args={"ssl": {"ca": str(settings.tidb_ca_path)}},
    # TiDB Cloud closes idle connections. These two settings make SQLAlchemy test a
    # connection before using it and replace old ones, instead of failing a request.
    pool_pre_ping=True,
    pool_recycle=300,
    # Keep slide text and other SQL values out of error messages and logs.
    hide_parameters=True,
)

# expire_on_commit=False: objects stay readable after commit, so we can build the
# JSON response from them without another trip to the database.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Parent class of all tables in app/models.py."""


def get_db():
    """FastAPI dependency: one database session per request, always closed at the end."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
