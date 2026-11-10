from fastapi import APIRouter

from app.api.routes import audit_logs, auth, dashboard, employees, notifications, settings, users

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(employees.router)
api_router.include_router(users.router)
api_router.include_router(notifications.router)
api_router.include_router(audit_logs.router)
api_router.include_router(settings.router)
api_router.include_router(dashboard.router)
