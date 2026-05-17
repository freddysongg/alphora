from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    cached_input_per_mtok: Decimal
    reasoning_per_mtok: Decimal


MODEL_PRICING: Mapping[str, ModelPricing] = {
    "gpt-5": ModelPricing(
        input_per_mtok=Decimal("1.25"),
        output_per_mtok=Decimal("10.00"),
        cached_input_per_mtok=Decimal("0.125"),
        reasoning_per_mtok=Decimal("10.00"),
    ),
    "gpt-5-mini": ModelPricing(
        input_per_mtok=Decimal("0.25"),
        output_per_mtok=Decimal("2.00"),
        cached_input_per_mtok=Decimal("0.025"),
        reasoning_per_mtok=Decimal("2.00"),
    ),
    "gpt-4o": ModelPricing(
        input_per_mtok=Decimal("2.50"),
        output_per_mtok=Decimal("10.00"),
        cached_input_per_mtok=Decimal("1.25"),
        reasoning_per_mtok=Decimal("10.00"),
    ),
    "gpt-4o-mini": ModelPricing(
        input_per_mtok=Decimal("0.15"),
        output_per_mtok=Decimal("0.60"),
        cached_input_per_mtok=Decimal("0.075"),
        reasoning_per_mtok=Decimal("0.60"),
    ),
}


class UnknownModelError(ValueError):
    """Raised when a model id is not present in MODEL_PRICING."""


def get_pricing(model_id: str) -> ModelPricing:
    pricing = MODEL_PRICING.get(model_id)
    if pricing is None:
        raise UnknownModelError(f"unknown model id: {model_id!r}")
    return pricing
