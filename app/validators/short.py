from typing import Any


def validate_short(
    normalized: dict,
    classification: Any,
    market_context: Any = None,
    ticker_context: Any = None
) -> dict:
    return {
        "decision": "WATCH",
        "reason": "short validator skeleton not implemented yet",
        "checks": {},
        "orderProposal": None
    }
