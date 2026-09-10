from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from os import getenv as ENV

load_dotenv()


def _getenv(Key: str, default=None):
    value = ENV(Key)
    if value:
        return value
    if default is not None:
        return default
    raise Exception(f"Value of key {Key} is not in Enviromnet")


# SQLite is the default so the backend runs with nothing installed.
#
# Previously all six settings were required, and a server database had to exist
# before the process could even import. That makes the system impossible to
# start and look at, which is the first thing anyone wants to do.
#
# There are now three ways to point this at a database, tried in order:
#
#   DATABASE_URL   one string. This is what Railway, Render, Fly and Heroku
#                  hand you, so a deployment needs no other database settings.
#   DRIVERNAME +   the six separate values, for a server you assembled yourself.
#   (nothing)      a SQLite file beside the backend.
_database_url = ENV("DATABASE_URL", "").strip()

if _database_url:
    # Several hosts still hand out the old "postgres://" prefix, which
    # SQLAlchemy refuses to parse. Rewriting it here means a working URL copied
    # straight from the dashboard does not have to be edited by hand.
    if _database_url.startswith("postgres://"):
        _database_url = _database_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif _database_url.startswith("postgresql://"):
        _database_url = _database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    SQL_ALCHEMY_URL = _database_url
    driver_name = "postgresql" if "postgres" in _database_url else _database_url.split(":")[0]
else:
    driver_name = _getenv("DRIVERNAME", "sqlite")

    if driver_name.startswith("sqlite"):
        # A file beside the backend, so data survives a restart.
        db_path = _getenv("DATABASE", "crovia.db")
        SQL_ALCHEMY_URL = URL.create(drivername="sqlite", database=db_path)
    else:
        SQL_ALCHEMY_URL = URL.create(
            drivername=driver_name,
            # DB_USERNAME is read first because USERNAME is a normal shell
            # variable on many systems. Reading it alone meant the database
            # login silently became whoever was logged into the machine.
            username=ENV("DB_USERNAME") or _getenv("USERNAME"),
            password=ENV("DB_PASSWORD") or _getenv("PASSWORD"),
            host=ENV("DB_HOST") or _getenv("HOST"),
            port=ENV("DB_PORT") or _getenv("PORT"),
            database=_getenv("DATABASE"),
        )


# echo=True prints every statement, which buries the application logs.
_echo = ENV("SQL_ECHO", "").lower() in ("1", "true", "yes")
_connect_args = {"check_same_thread": False} if driver_name.startswith("sqlite") else {}
# pool_pre_ping checks a connection before handing it out. Managed Postgres
# closes idle connections, and without this the first request after a quiet
# period fails with "server closed the connection unexpectedly".
engine = create_engine(SQL_ALCHEMY_URL, echo=_echo, connect_args=_connect_args,
                       pool_pre_ping=not driver_name.startswith("sqlite"))

session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

base = declarative_base()


def getdb():
    db = session()
    try:
        yield db
    finally:
        db.close()


def create_table():
    base.metadata.create_all(bind=engine)
