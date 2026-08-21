from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from merge_review.config import get_settings
from merge_review.database import create_schema


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_schema()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
