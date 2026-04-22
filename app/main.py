from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.indexes import create_indexes
from app.db.migrations import migrate_legacy_chat_storage
from app.db.mongodb import mongo_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongo_database.connect()
    await migrate_legacy_chat_storage(mongo_database.db)
    await create_indexes(mongo_database.db)
    yield
    await mongo_database.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolved_backend_cors_origins,
        allow_origin_regex=settings.resolved_backend_cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
