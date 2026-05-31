from typing import Any, Dict, Optional

from app.market_data.indicators import calculate_indicators
from app.market_data.provider import get_market_context
from app.validators.ultra_short import build_ultra_short_gex_trade_plan


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


def _build_trade_plan(
    normalized_alert: Dict[str, Any],
    classification: Dict[str, Any],
    market_context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    strategy = classification.get("strategy")
    if strategy != "ultra_short":
        return None

    gex_context = market_context.get("gex_context") or market_context.get("gex")
    if not gex_context:
        return None

    underlying = market_context.get("underlying") or {}
    alert_side = (normalized_alert.get("option") or {}).get("type")
    return build_ultra_short_gex_trade_plan(
        alert_side,
        underlying.get("price"),
        gex_context,
    )


def _selected_walls(trade_plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    selected_wall_above = None
    selected_wall_below = None

    if isinstance(trade_plan, dict):
        for wall in (
            trade_plan.get("targetWall"),
            trade_plan.get("stopWall"),
            trade_plan.get("checkpointWall"),
        ):
            summary = _summarize_wall(wall)
            if _wall_position(wall) == "above" and selected_wall_above is None:
                selected_wall_above = summary
            if _wall_position(wall) == "below" and selected_wall_below is None:
                selected_wall_below = summary

    return {
        "selectedWallAbove": selected_wall_above,
        "selectedWallBelow": selected_wall_below,
    }


def _risk_reward(normalized_alert: Dict[str, Any], trade_plan: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(trade_plan, dict):
        return None

    entry = _safe_float(trade_plan.get("entry"))
    stop = _safe_float(trade_plan.get("stop"))
    target = _safe_float(trade_plan.get("target"))
    alert_side = (normalized_alert.get("option") or {}).get("type")

    if entry is None or stop is None or target is None:
        return None

    if alert_side == "CALL":
        risk = entry - stop
        reward = target - entry
    elif alert_side == "PUT":
        risk = stop - entry
        reward = entry - target
    else:
        return None

    if risk <= 0 or reward <= 0:
        return None

    return reward / risk


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

    option = market_context.get("option") or {}
    underlying = market_context.get("underlying") or {}
    gex_context = market_context.get("gex_context")
    trade_plan = _build_trade_plan(normalized_alert, classification, market_context)
    selected_walls = _selected_walls(trade_plan)

    return {
        "underlyingPrice": underlying.get("price"),
        "option": _camel_option(option),
        "priceDeviationPct": raw_indicators.get("price_deviation_pct"),
        "spreadPct": raw_indicators.get("spread_pct"),
        "spreadAbs": raw_indicators.get("spread"),
        "liquidityScore": None,
        "entry": trade_plan.get("entry") if isinstance(trade_plan, dict) else None,
        "stop": trade_plan.get("stop") if isinstance(trade_plan, dict) else None,
        "target": trade_plan.get("target") if isinstance(trade_plan, dict) else None,
        "riskReward": _risk_reward(normalized_alert, trade_plan),
        "gex": {
            "walls": selected_walls,
            "allWalls": _all_walls(gex_context),
        },
        "dataQuality": {
            "underlyingOk": underlying.get("price") is not None,
            "optionQuoteOk": option.get("bid") is not None and option.get("ask") is not None,
            "optionChainOk": bool(market_context.get("optionChain")),
            "gexOk": bool(gex_context),
            "missingFields": _missing_fields(market_context, raw_indicators),
        },
    }


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
