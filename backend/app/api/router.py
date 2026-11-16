from fastapi import APIRouter

from app.api.routes import (
    analysis,
    analytics,
    applicants,
    assessments,
    applications,
    audit_logs,
    auth,
    bulk,
    categories,
    dashboard,
    employees,
    jobs,
    notifications,
    openings,
    question_bank,
    evaluations,
    interviews,
    resumes,
    schedules,
    settings,
    tests,
    users,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(employees.router)
api_router.include_router(users.router)
api_router.include_router(notifications.router)
api_router.include_router(audit_logs.router)
api_router.include_router(settings.router)
api_router.include_router(dashboard.router)
api_router.include_router(categories.router)
api_router.include_router(openings.router)
api_router.include_router(jobs.router)
api_router.include_router(applicants.router)
api_router.include_router(resumes.router)
api_router.include_router(applications.router)
api_router.include_router(analysis.router)
api_router.include_router(assessments.router)
api_router.include_router(question_bank.router)
api_router.include_router(schedules.router)
api_router.include_router(tests.router)
api_router.include_router(evaluations.router)
api_router.include_router(interviews.router)
api_router.include_router(bulk.router)
api_router.include_router(bulk.item_router)
api_router.include_router(analytics.router)
