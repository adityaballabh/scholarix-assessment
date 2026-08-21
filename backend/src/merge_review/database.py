from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from merge_review.config import get_settings
from merge_review.models import Base

engine = create_engine(get_settings().database_url)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


def create_schema() -> None:
    Base.metadata.create_all(engine)
