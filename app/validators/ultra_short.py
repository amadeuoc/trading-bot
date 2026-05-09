from typing import Any


def validate_ultra_short(
    normalized: dict,
    classification: Any,
    market_context: Any = None,
    ticker_context: Any = None
) -> dict:
    return {
        "decision": "WATCH",
        "reason": "ultra_short validator skeleton not implemented yet",
        "checks": {},
        "orderProposal": None
    }
