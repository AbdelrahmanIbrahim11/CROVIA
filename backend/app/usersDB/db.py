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
# start and look at, which is the first thing anyone wants to do. Point
# DRIVERNAME at postgresql+psycopg2 and fill in the rest for a real deployment.
driver_name = _getenv("DRIVERNAME", "sqlite")

if driver_name.startswith("sqlite"):
    # A file beside the backend, so data survives a restart.
    db_path = _getenv("DATABASE", "crovia.db")
    SQL_ALCHEMY_URL = URL.create(drivername="sqlite", database=db_path)
else:
    SQL_ALCHEMY_URL = URL.create(
        drivername=driver_name,
        username=_getenv("USERNAME"),
        password=_getenv("PASSWORD"),
        host=_getenv("HOST"),
        port=_getenv("PORT"),
        database=_getenv("DATABASE"),
    )


# echo=True prints every statement, which buries the application logs.
_echo = ENV("SQL_ECHO", "").lower() in ("1", "true", "yes")
_connect_args = {"check_same_thread": False} if driver_name.startswith("sqlite") else {}
engine = create_engine(SQL_ALCHEMY_URL, echo=_echo, connect_args=_connect_args)

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
