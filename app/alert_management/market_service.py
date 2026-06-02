from typing import Any, Dict, Optional

from app.market_data.indicators import calculate_indicators
from app.market_data.provider import get_market_context


def _public_gex_context(gex_context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(gex_context, dict):
        return None

    return {
        "source": gex_context.get("source"),
        "spot": gex_context.get("spot"),
        "dteMax": gex_context.get("dte_max"),
        "rangePct": gex_context.get("range_pct"),
        "points": gex_context.get("points") or [],
        "walls": gex_context.get("walls") or [],
    }


def _public_market_data(market_context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "option": market_context.get("option") or {},
        "underlying": market_context.get("underlying") or {},
        "optionChain": market_context.get("optionChain") or [],
        "gexContext": _public_gex_context(market_context.get("gex_context")),
    }


def build_indicators_contract(
    normalized_alert: Dict[str, Any],
    classification: Dict[str, Any],
    market_context: Dict[str, Any],
) -> Dict[str, Any]:
    raw_indicators = calculate_indicators(normalized_alert, market_context)
    market_context["indicators"] = raw_indicators

    return raw_indicators


def get_market_data_and_indicators(
    normalized_alert: Dict[str, Any],
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    market_context = get_market_context(normalized_alert, classification)
    indicators = build_indicators_contract(
        normalized_alert,
        classification,
        market_context,
    )

    return {
        "status": "ok",
        "marketData": _public_market_data(market_context),
        "indicators": indicators,
    }
