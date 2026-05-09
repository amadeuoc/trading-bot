from typing import Any


def validate_leap(
    normalized: dict,
    classification: Any,
    market_context: Any = None,
    ticker_context: Any = None
) -> dict:
    return {
        "decision": "WATCH",
        "reason": "leap validator skeleton not implemented yet",
        "checks": {},
        "orderProposal": None
    }
