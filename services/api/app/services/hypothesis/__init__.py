"""Phase 4 — hypothesis lifecycle runtime.

Submodules:
- `embedding`: `Embedder` Protocol + `OpenAiEmbedder` + `cosine_similarity` helper.
- `dedup`: embedding-driven dedup at hypothesis creation with optional LLM
  confirmation before merging or superseding an existing hypothesis.
- `lifecycle`: belief-floor archival, stagnation flagging, valid-until expiry,
  parent/child wiring and active → validated / falsified auto-transitions.
- `events`: event-resolution ingestion + fan-out to bound hypotheses via
  `validates_if_beat` / `falsifies_if_miss` conditional edges.
"""

from app.services.hypothesis.dedup import (
    DEDUP_MODEL_DEFAULT,
    DEDUP_PROMPT_VERSION,
    DEFAULT_SIMILARITY_THRESHOLD,
    DedupAction,
    DedupOutcome,
    DedupVerdict,
    DuplicateCandidate,
    DuplicateConfirmer,
    OpenAiDuplicateConfirmer,
    find_duplicate_candidates,
    resolve_duplicate,
)
from app.services.hypothesis.embedding import (
    DEFAULT_EMBEDDING_MODEL,
    Embedder,
    OpenAiEmbedder,
    cosine_similarity,
    l2_normalize,
)
from app.services.hypothesis.events import (
    apply_event_resolution,
    apply_outcome_to_hypothesis,
    record_event_resolution,
)
from app.services.hypothesis.lifecycle import (
    BELIEF_FLOOR,
    FALSIFY_THRESHOLD,
    STAGNATION_THRESHOLD_DAYS,
    VALIDATE_THRESHOLD,
    LifecycleSweepReport,
    bump_last_activity,
    run_lifecycle_sweep,
)

__all__ = [
    "BELIEF_FLOOR",
    "DEDUP_MODEL_DEFAULT",
    "DEDUP_PROMPT_VERSION",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "FALSIFY_THRESHOLD",
    "STAGNATION_THRESHOLD_DAYS",
    "VALIDATE_THRESHOLD",
    "DedupAction",
    "DedupOutcome",
    "DedupVerdict",
    "DuplicateCandidate",
    "DuplicateConfirmer",
    "Embedder",
    "LifecycleSweepReport",
    "OpenAiDuplicateConfirmer",
    "OpenAiEmbedder",
    "apply_event_resolution",
    "apply_outcome_to_hypothesis",
    "bump_last_activity",
    "cosine_similarity",
    "find_duplicate_candidates",
    "l2_normalize",
    "record_event_resolution",
    "resolve_duplicate",
    "run_lifecycle_sweep",
]
