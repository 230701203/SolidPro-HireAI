import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.database import SessionLocal

log = logging.getLogger("hireai.sweeper")


def _sweep_once() -> None:
    from app.services import attempt_service, bulk_service, evaluation_service

    with SessionLocal() as db:
        result = {**attempt_service.sweep(db), **evaluation_service.sweep(db), **bulk_service.sweep(db)}
        if any(result.values()):
            log.info("sweeper: %s", result)


async def _sweeper_loop(interval: int) -> None:
    while True:
        try:
            await asyncio.to_thread(_sweep_once)
        except Exception:  # never let one bad pass stop the loop
            log.exception("sweeper pass failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Auto-submit overdue attempts and expire missed schedules even when nobody is looking at them.

    Runs inside the API process (fine for a single instance). With several instances, set SWEEPER_ENABLED=false
    on all but one, or move `attempt_service.sweep` to a cron job.
    """
    s = get_settings()
    task = asyncio.create_task(_sweeper_loop(max(15, s.sweeper_interval_seconds))) if s.sweeper_enabled and s.environment != "test" else None
    try:
        yield
    finally:
        if task:
            task.cancel()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=f"{s.app_name} API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Attempt-Session"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/api") and not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/api/health", tags=["Health"])
    def health():
        with SessionLocal() as db:
            db.execute(text("select 1"))
        return {"status": "ok"}

    return app


app = create_app()
