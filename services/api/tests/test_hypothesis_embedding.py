import math

import pytest

from app.services.hypothesis.embedding import (
    cosine_similarity,
    l2_normalize,
)


def test_l2_normalize_returns_unit_vector() -> None:
    out = l2_normalize([3.0, 4.0])
    assert pytest.approx(out[0]) == 0.6
    assert pytest.approx(out[1]) == 0.8
    assert pytest.approx(math.sqrt(out[0] ** 2 + out[1] ** 2)) == 1.0


def test_l2_normalize_returns_input_for_zero_vector() -> None:
    assert l2_normalize([0.0, 0.0, 0.0]) == [0.0, 0.0, 0.0]


def test_cosine_similarity_is_one_for_identical_unit_vectors() -> None:
    vector = l2_normalize([0.5, 0.5, 0.5, 0.5])
    assert pytest.approx(cosine_similarity(vector, vector)) == 1.0


def test_cosine_similarity_is_zero_for_orthogonal_vectors() -> None:
    assert pytest.approx(cosine_similarity([1.0, 0.0], [0.0, 1.0])) == 0.0


def test_cosine_similarity_is_minus_one_for_opposed_vectors() -> None:
    assert pytest.approx(cosine_similarity([1.0, 0.0], [-1.0, 0.0])) == -1.0


def test_cosine_similarity_returns_zero_for_mismatched_length() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


def test_cosine_similarity_returns_zero_for_empty_vectors() -> None:
    assert cosine_similarity([], []) == 0.0


def test_cosine_similarity_returns_zero_when_one_side_is_all_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
