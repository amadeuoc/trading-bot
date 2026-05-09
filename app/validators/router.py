from typing import Any, Optional

from app.validators.leap import validate_leap
from app.validators.short import validate_short
from app.validators.swing import validate_swing
from app.validators.ultra_short import validate_ultra_short


def _get_strategy(classification: Any) -> Optional[str]:
    if isinstance(classification, dict):
        return classification.get("strategy")
    return getattr(classification, "strategy", None)


def validate_by_strategy(
    normalized: dict,
    classification: Any,
    market_context: Any = None,
    ticker_context: Any = None
) -> dict:
    strategy = _get_strategy(classification)

    if strategy == "ultra_short":
        return validate_ultra_short(normalized, classification, market_context, ticker_context)
    if strategy == "short":
        return validate_short(normalized, classification, market_context, ticker_context)
    if strategy == "swing":
        return validate_swing(normalized, classification, market_context, ticker_context)
    if strategy == "leap":
        return validate_leap(normalized, classification, market_context, ticker_context)

    return {
        "decision": "SKIP",
        "reason": "Unknown strategy",
        "checks": {},
        "orderProposal": None
    }
