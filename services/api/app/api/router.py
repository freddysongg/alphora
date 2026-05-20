from fastapi import APIRouter

from app.api.routes import (
    company_theses,
    data_health,
    graph,
    health,
    hypotheses,
    macro_briefs,
    paper,
    portfolio_briefs,
    research_runs,
    screeners,
    sector_briefs,
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
api_router.include_router(
    portfolio_briefs.router, prefix="/research-runs", tags=["research-runs"]
)
api_router.include_router(
    sector_briefs.router, prefix="/research-runs", tags=["research-runs"]
)
api_router.include_router(
    company_theses.router, prefix="/research-runs", tags=["research-runs"]
)
api_router.include_router(
    hypotheses.router, prefix="/research", tags=["research"]
)
api_router.include_router(graph.router, prefix="/research", tags=["research"])
api_router.include_router(screeners.router, prefix="/screeners", tags=["screeners"])
api_router.include_router(paper.router, prefix="/paper", tags=["paper"])
api_router.include_router(
    data_health.router, prefix="/data-health", tags=["data-health"]
)
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(
    watchlists.router, prefix="/watchlists", tags=["watchlists"]
)
