"""Embedding helpers for hypothesis dedup.

`Embedder` is a Protocol so production code can wire `OpenAiEmbedder`
(`text-embedding-3-small` by default) while tests can supply a deterministic
in-memory embedder. The embedding is stored on `Hypothesis.embedding` as an
L2-normalised list of floats so cosine similarity is a plain dot product.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol, cast

from openai import AsyncOpenAI

DEFAULT_EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]:
        """Return an L2-normalised embedding for `text`."""
        ...


@dataclass(frozen=True)
class OpenAiEmbedder:
    """OpenAI-backed embedder. Always returns L2-normalised vectors."""

    client: AsyncOpenAI
    model: str = DEFAULT_EMBEDDING_MODEL

    async def embed(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model=self.model, input=text
        )
        data = response.data
        if not data:
            raise EmbeddingError(
                f"embedding response from {self.model!r} had no data items"
            )
        raw = cast(Sequence[float], data[0].embedding)
        if not raw:
            raise EmbeddingError(
                f"embedding from {self.model!r} returned an empty vector"
            )
        return l2_normalize(list(raw))


class EmbeddingError(Exception):
    """Raised when an embedding cannot be produced."""


def l2_normalize(vector: Sequence[float]) -> list[float]:
    """Return a copy of `vector` divided by its L2 norm.

    An all-zero vector is returned unchanged — there is no meaningful
    direction to normalise to, and producing NaNs would poison downstream
    cosine math.
    """
    norm_sq = 0.0
    for value in vector:
        norm_sq += value * value
    if norm_sq <= 0.0:
        return list(vector)
    norm = math.sqrt(norm_sq)
    return [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Cosine similarity in `[-1, 1]` for two equal-length vectors.

    Returns `0.0` for a length mismatch or when either side is the zero
    vector — both are treated as "not comparable" rather than raising, so
    the dedup pipeline can keep moving when historical embeddings are
    absent or malformed.
    """
    if len(left) != len(right) or not left:
        return 0.0
    dot = 0.0
    left_sq = 0.0
    right_sq = 0.0
    for left_value, right_value in zip(left, right, strict=False):
        dot += left_value * right_value
        left_sq += left_value * left_value
        right_sq += right_value * right_value
    if left_sq <= 0.0 or right_sq <= 0.0:
        return 0.0
    denom = math.sqrt(left_sq) * math.sqrt(right_sq)
    return dot / denom


__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "Embedder",
    "EmbeddingError",
    "OpenAiEmbedder",
    "cosine_similarity",
    "l2_normalize",
]
