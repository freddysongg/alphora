from fastapi import APIRouter

from app.api.routes import (
    data_health,
    health,
    macro_briefs,
    paper,
    research_runs,
    screeners,
    settings,
    watchlists,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(
    research_runs.router, prefix="/research-runs", tags=["research-runs"]
)
api_router.include_router(
    macro_briefs.router, prefix="/research-runs", tags=["research-runs"]
)
api_router.include_router(screeners.router, prefix="/screeners", tags=["screeners"])
api_router.include_router(paper.router, prefix="/paper", tags=["paper"])
api_router.include_router(
    data_health.router, prefix="/data-health", tags=["data-health"]
)
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(
    watchlists.router, prefix="/watchlists", tags=["watchlists"]
)
