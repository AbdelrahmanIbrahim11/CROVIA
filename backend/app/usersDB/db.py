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
        # A deployment must never land here.
        #
        # A hosted container's disk is wiped on every restart, and these
        # services restart often - a deploy, a crash, or simply waking from
        # sleep. SQLite there means every account silently disappears, and the
        # only symptom is people being unable to sign in to an account they
        # made yesterday. Refusing is better than losing their data quietly.
        if ENV("CROVIA_ENV", "local").lower() != "local":
            raise RuntimeError(
                "DATABASE_URL must be set when CROVIA_ENV is not 'local'. "
                "A hosted disk is erased on restart, so SQLite would lose "
                "every account without warning.")
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


def drop_username_uniqueness() -> None:
    """
    Let two people share a name.

    The username column was created UNIQUE, which meant the second Ahmed to
    sign up got a 500 - an IntegrityError on a column nobody thinks of as an
    identifier. A display name is not an identifier; the email is, and that is
    unique already.

    create_all() only creates missing tables, so an existing database keeps the
    old constraint until it is dropped here. Written to be safe to run every
    startup and on either database: nothing happens if the constraint is
    already gone, and SQLite has no such constraint to drop.
    """
    from sqlalchemy import inspect, text

    if driver_name.startswith("sqlite"):
        return
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in ("normal_users", "admin_users", "authority_users"):
            if table not in insp.get_table_names():
                continue
            for uc in insp.get_unique_constraints(table):
                if uc.get("column_names") == ["username"] and uc.get("name"):
                    conn.execute(text(
                        f'ALTER TABLE {table} DROP CONSTRAINT "{uc["name"]}"'))
