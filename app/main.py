from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, payments, tariffs, webhooks
from app.api.errors import register_error_handlers
from app.db.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # Close pooled connections gracefully on shutdown.
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kvitto Payments API",
        version="0.1.0",
        description="Payment acceptance for online course tariffs.",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(tariffs.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    register_error_handlers(app)
    return app


app = create_app()
