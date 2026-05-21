class FunnelResearchError(Exception):
    """Raised when the funnel strategy cannot return a usable result."""


class FunnelResearchBudgetHaltError(FunnelResearchError):
    """Raised when a sector/company synthesis or judge call is aborted by a
    budget pause/kill. Pause/fail has already been routed through the
    orchestrator before this is raised — the fan-out caller must cancel its
    sibling workers and propagate so `_run_funnel` returns silently."""


__all__ = ["FunnelResearchBudgetHaltError", "FunnelResearchError"]
