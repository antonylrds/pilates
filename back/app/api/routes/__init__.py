from fastapi import APIRouter

from app.api.routes import (
    auth,
    calendar,
    catalog,
    class_groups,
    documents,
    notifications,
    offerings,
    payments,
    platform,
    reports,
    studio,
    students,
    teachers,
    users,
)

api_router = APIRouter()
api_router.include_router(platform.router)
for module in (
    auth, studio, users, catalog, offerings, teachers, students, class_groups, calendar, notifications, reports,
    payments, documents,
):
    api_router.include_router(module.router)
