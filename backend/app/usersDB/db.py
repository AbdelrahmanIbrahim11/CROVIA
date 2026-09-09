from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from os import getenv as ENV

load_dotenv()


def _getenv(Key: str):
    value = ENV(Key)

    if value:
        return value
    else:
        raise Exception(f"Value of key {Key} is not in Enviromnet")


driver_name = _getenv("DRIVERNAME")
username = _getenv("USERNAME")
password = _getenv("PASSWORD")
host = _getenv("HOST")
port = _getenv("PORT")
database = _getenv("DATABASE")

SQL_ALCHEMY_URL = URL.create(
    drivername=driver_name,
    username=username,
    password=password,
    host=host,
    port=port,
    database=database,
)


engine = create_engine(SQL_ALCHEMY_URL, echo=True)

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
