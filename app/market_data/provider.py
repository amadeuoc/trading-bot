from typing import Any, Dict

from app.market_data.ultra_short import get_ultra_short_market_context


def _empty_market_context() -> Dict[str, Any]:
    return {
        "option": {
            "ask": None,
            "bid": None,
            "volume": None,
            "open_interest": None,
        },
        "underlying": {
            "price": None,
        },
        "optionChain": [],
    }


def get_market_context(normalized: dict, classification: dict) -> Dict[str, Any]:
    strategy = classification.get("strategy") if isinstance(classification, dict) else None

    if strategy == "ultra_short":
        return get_ultra_short_market_context(normalized)

    return _empty_market_context()
