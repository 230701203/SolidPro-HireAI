from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.database import SessionLocal


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=f"{s.app_name} API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
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
