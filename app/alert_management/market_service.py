from typing import Any, Dict, Optional

from app.market_data.indicators import calculate_indicators
from app.market_data.provider import get_market_context


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _camel_option(option: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bid": option.get("bid"),
        "ask": option.get("ask"),
        "last": option.get("last"),
        "volume": option.get("volume"),
        "openInterest": option.get("open_interest"),
    }


def _wall_position(wall: Optional[Dict[str, Any]]) -> Optional[str]:
    return wall.get("position") if isinstance(wall, dict) else None


def _summarize_wall(wall: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(wall, dict):
        return None

    return {
        "strike": wall.get("strike"),
        "position": wall.get("position"),
        "distanceFromSpot": wall.get("distance_from_spot"),
        "distancePctFromSpot": wall.get("distance_pct_from_spot"),
        "hybridStrength": wall.get("hybrid_strength"),
        "sign": wall.get("sign"),
        "behavior": wall.get("behavior"),
    }


def _all_walls(gex_context: Optional[Dict[str, Any]]) -> list:
    if not isinstance(gex_context, dict):
        return []
    return [
        _summarize_wall(wall)
        for wall in gex_context.get("walls") or []
        if isinstance(wall, dict)
    ]


def _missing_fields(market_context: Dict[str, Any], indicators: Dict[str, Any]) -> list:
    missing = []
    option = market_context.get("option") or {}
    underlying = market_context.get("underlying") or {}

    for field in ("bid", "ask", "volume"):
        if option.get(field) is None:
            missing.append(f"option.{field}")
    if option.get("open_interest") is None:
        missing.append("option.open_interest")
    if underlying.get("price") is None:
        missing.append("underlying.price")
    if indicators.get("price_deviation_pct") is None:
        missing.append("price_deviation_pct")
    if indicators.get("spread_pct") is None:
        missing.append("spread_pct")

    return missing


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
        "marketContext": market_context,
        "indicators": indicators,
    }
