from fastapi import APIRouter

from app.api.routes import (
    approvals,
    company_theses,
    data_health,
    evals,
    events,
    graph,
    health,
    human_reviews,
    hypotheses,
    macro_briefs,
    observability,
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
    approvals.router, prefix="/approvals", tags=["approvals"]
)
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
api_router.include_router(events.router, prefix="/research", tags=["research"])
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
api_router.include_router(evals.router, tags=["evals"])
api_router.include_router(human_reviews.router, tags=["human-reviews"])
api_router.include_router(observability.router, tags=["observability"])
