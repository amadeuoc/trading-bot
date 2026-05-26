from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.classify import classify_alert
from app.market_data.indicators import calculate_indicators
from app.market_data.provider import get_market_context
from app.validators.router import validate_by_strategy


MARKET_TZ = ZoneInfo("America/New_York")


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _timestamp_to_market_datetime(timestamp):
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return None

    # Support milliseconds if needed.
    if ts > 10_000_000_000:
        ts = ts / 1000

    return datetime.fromtimestamp(ts, MARKET_TZ)


def _is_alert_from_market_today(normalized: dict) -> bool:
    alert = normalized.get("alert") or {}
    alert_dt = _timestamp_to_market_datetime(alert.get("timestamp"))

    if alert_dt is None:
        return False

    now = datetime.now(MARKET_TZ)
    return alert_dt.date() == now.date()


def _rejected_response(normalized: dict, reason: str) -> dict:
    validation = {
        "validator": None,
        "decision": "REJECT",
        "checks": [],
        "failedChecks": [],
        "orderProposal": None,
    }
    return _build_analyze_response(
        normalized=normalized,
        classification=None,
        market_context=None,
        strategy_validation=validation,
        decision="REJECT",
        reason=reason,
    )


def _get_ticker_context(classification):
    if isinstance(classification, dict):
        return classification.get("tickerAlertsToday")
    return getattr(classification, "tickerAlertsToday", None)


def _serialize_market_context(market_context):
    if market_context is None:
        return None
    if hasattr(market_context, "model_dump"):
        return market_context.model_dump()
    return market_context


def _attach_indicators(normalized: dict, classification: dict, market_context):
    if not isinstance(market_context, dict):
        return

    strategy = classification.get("strategy") if isinstance(classification, dict) else None
    if strategy != "ultra_short":
        return

    try:
        market_context["indicators"] = calculate_indicators(normalized, market_context)
    except Exception as exc:
        market_context["indicators"] = {}
        market_context["indicatorError"] = str(exc)


def _get_final_decision(strategy_validation: dict) -> tuple[str, str]:
    if isinstance(strategy_validation, dict):
        decision = strategy_validation.get("decision")
        reason = strategy_validation.get("reason")

        if decision in ("VALID", "REJECT", "SKIP", "WATCH"):
            return decision, reason or "Strategy validation completed"

    return "REJECT", "Strategy validation unavailable"


def _camelize_known(value: Any):
    if isinstance(value, list):
        return [_camelize_known(item) for item in value]
    if not isinstance(value, dict):
        return value

    key_map = {
        "spread_execution": "spreadExecution",
        "price_deviation_pct": "priceDeviationPct",
        "spread_pct": "spreadPct",
        "risk_reward": "riskReward",
        "target_source": "targetSource",
        "option_type": "type",
        "open_interest": "openInterest",
        "is_alert_contract": "isAlertContract",
        "distance_from_spot": "distanceFromSpot",
        "distance_pct_from_spot": "distancePctFromSpot",
        "oi_gex": "oiGex",
        "volume_gex": "volumeGex",
        "hybrid_gex": "hybridGex",
        "hybrid_strength": "hybridStrength",
        "call_hybrid_gex": "callHybridGex",
        "put_hybrid_gex": "putHybridGex",
        "net_hybrid_gex": "netHybridGex",
        "call_strength": "callStrength",
        "put_strength": "putStrength",
        "dominant_side": "dominantSide",
        "signed_flow_gex": "signedFlowGex",
        "signed_flow_gex_total": "signedFlowGexTotal",
        "sign_score": "signScore",
        "dte_max": "dteMax",
        "nearest_above": "nearestAbove",
        "nearest_below": "nearestBelow",
        "strongest_wall_above": "strongestWallAbove",
        "strongest_wall_below": "strongestWallBelow",
        "nearest_trade_wall_above": "nearestTradeWallAbove",
        "nearest_trade_wall_below": "nearestTradeWallBelow",
        "strongest_trade_wall_above": "strongestTradeWallAbove",
        "strongest_trade_wall_below": "strongestTradeWallBelow",
        "strongest_call_wall": "strongestCallWall",
        "strongest_put_wall": "strongestPutWall",
    }
    return {
        key_map.get(key, key): _camelize_known(item)
        for key, item in value.items()
    }


def _build_received(normalized: dict) -> dict:
    trade = normalized.get("trade") or {}
    return {
        "alert": normalized.get("alert") or {},
        "contract": normalized.get("option") or {},
        "trade": {
            "price": trade.get("price"),
            "premium": trade.get("premium"),
            "spreadExecution": trade.get("spread_execution"),
        },
    }


def _build_alert_context(normalized: dict, classification) -> dict:
    option = normalized.get("option") or {}
    alerts_today = []
    if isinstance(classification, dict):
        alerts_today = classification.get("tickerAlertsToday") or []

    return {
        "underlying": option.get("underlying") or normalized.get("underlying"),
        "alertsTodayCount": len(alerts_today),
        "underlyingAlertsToday": _camelize_known(alerts_today),
    }


def _build_classification(normalized: dict, classification) -> dict:
    if not isinstance(classification, dict):
        return {}

    option = normalized.get("option") or {}
    return {
        "sentiment": classification.get("sentiment"),
        "strategy": classification.get("strategy"),
        "dte": classification.get("dte"),
        "contractType": option.get("type"),
    }


def _build_market_data(market_context, classification) -> dict:
    market_context = market_context if isinstance(market_context, dict) else {}
    strategy = classification.get("strategy") if isinstance(classification, dict) else None
    option_chain = market_context.get("optionChain") or []
    option = dict(market_context.get("option") or {})
    alert_contract = next(
        (
            row for row in option_chain
            if isinstance(row, dict) and row.get("is_alert_contract") is True
        ),
        None
    )

    if alert_contract:
        fill_fields = {
            "gamma": "gamma",
            "open_interest": "open_interest",
            "volume": "volume",
            "bid": "bid",
            "ask": "ask",
            "last": "last",
        }
        for option_key, chain_key in fill_fields.items():
            if option.get(option_key) is None:
                option[option_key] = alert_contract.get(chain_key)

    return {
        "source": "ibkr" if strategy == "ultra_short" else None,
        "option": _camelize_known(option),
        "underlying": market_context.get("underlying") or {},
        "optionChain": [
            _camelize_known(row)
            for row in option_chain
        ],
    }


def _wall_key(wall):
    if not isinstance(wall, dict):
        return None
    return (
        wall.get("strike"),
        wall.get("position"),
        wall.get("behavior"),
    )


def _strike_key(wall):
    if not isinstance(wall, dict):
        return None
    return wall.get("strike")


def _summarize_wall(wall):
    if not isinstance(wall, dict):
        return None

    distance = _safe_float(
        wall.get("distance_from_spot")
        if "distance_from_spot" in wall
        else wall.get("distanceFromSpot")
    )

    return {
        "strike": wall.get("strike"),
        "dominantSide": wall.get("dominant_side") or wall.get("dominantSide"),
        "position": wall.get("position"),
        "distanceFromSpot": abs(distance) if distance is not None else None,
        "hybridStrength": wall.get("hybrid_strength") or wall.get("hybridStrength"),
        "behavior": wall.get("behavior"),
    }


def _build_trade_walls(strategy_validation) -> dict:
    order = strategy_validation.get("orderProposal") if isinstance(strategy_validation, dict) else None
    walls = order.get("gexWalls") if isinstance(order, dict) else {}

    return {
        "targetWall": _summarize_wall((walls or {}).get("targetWall")),
        "stopWall": _summarize_wall((walls or {}).get("stopWall")),
    }


def _build_strike_range(gex: dict) -> dict:
    spot = gex.get("spot")
    range_pct = gex.get("range_pct")

    if spot is None or range_pct is None:
        return {
            "percent": None,
            "lowerBound": None,
            "upperBound": None,
        }

    return {
        "percent": range_pct * 100,
        "lowerBound": spot * (1 - range_pct),
        "upperBound": spot * (1 + range_pct),
    }


def _build_significant_levels(gex: dict, trade_walls: dict) -> list:
    walls = gex.get("walls") or []
    selected_keys = {
        key for key in (
            _wall_key(trade_walls.get("targetWall")),
            _wall_key(trade_walls.get("stopWall")),
        )
        if key is not None
    }
    significant = [
        wall for wall in walls
        if isinstance(wall, dict)
        and (
            (wall.get("hybrid_strength") or 0) > 0
            or _wall_key(wall) in selected_keys
        )
    ]

    return [
        _summarize_wall(wall)
        for wall in sorted(
            significant,
            key=lambda item: item.get("strike") or 0
        )
    ]


def _build_gex_levels(gex: dict, market_context: dict, trade_walls: dict) -> list:
    walls = gex.get("walls") or []
    option_chain = market_context.get("optionChain") or []

    alert_contract_strikes = {
        _strike_key(row): row
        for row in option_chain
        if isinstance(row, dict) and row.get("is_alert_contract") is True
    }
    target_key = _wall_key(trade_walls.get("targetWall"))
    stop_key = _wall_key(trade_walls.get("stopWall"))
    relevant_wall_keys = {key for key in (target_key, stop_key) if key is not None}
    above_walls = [
        wall for wall in walls
        if isinstance(wall, dict) and wall.get("position") == "above"
    ]
    below_walls = [
        wall for wall in walls
        if isinstance(wall, dict) and wall.get("position") == "below"
    ]
    top_above = sorted(
        above_walls,
        key=lambda wall: wall.get("hybrid_strength") or 0,
        reverse=True
    )[:3]
    top_below = sorted(
        below_walls,
        key=lambda wall: wall.get("hybrid_strength") or 0,
        reverse=True
    )[:3]
    relevant_wall_keys.update(
        key for key in (_wall_key(wall) for wall in top_above + top_below)
        if key is not None
    )

    levels = []
    for wall in walls:
        key = _wall_key(wall)
        order_role = None
        is_target_wall = key == target_key
        is_stop_wall = key == stop_key
        if is_target_wall:
            order_role = "target_wall"
        elif is_stop_wall:
            order_role = "stop_wall"

        level = {
            **wall,
            "flags": {
                "alertContract": _strike_key(wall) in alert_contract_strikes,
                "wall": key in relevant_wall_keys,
                "targetWall": is_target_wall,
                "stopWall": is_stop_wall,
            },
            "orderRole": order_role,
        }
        levels.append(_camelize_known(level))

    return levels


def _build_gex_indicators(market_context: dict, strategy_validation) -> dict:
    indicators = market_context.get("indicators") or {}
    gex = indicators.get("gex") or market_context.get("gex_context")
    if not isinstance(gex, dict):
        return {}

    trade_walls = _build_trade_walls(strategy_validation)
    return {
        "source": gex.get("source"),
        "spot": gex.get("spot"),
        "dteMax": gex.get("dte_max"),
        "strikeRange": _build_strike_range(gex),
        "significantLevels": _build_significant_levels(gex, trade_walls),
        "levels": _build_gex_levels(gex, market_context, trade_walls),
        "tradeWalls": trade_walls,
    }


def _build_indicators(market_context, strategy_validation) -> dict:
    market_context = market_context if isinstance(market_context, dict) else {}
    indicators = market_context.get("indicators") or {}

    return {
        "priceDeviationPct": indicators.get("price_deviation_pct"),
        "spread": indicators.get("spread"),
        "spreadPct": indicators.get("spread_pct"),
        "liquidity": _camelize_known(indicators.get("liquidity") or {}),
        "gex": _build_gex_indicators(market_context, strategy_validation),
    }


def _summarize_gex_level_for_validation(level: dict) -> dict:
    flags = level.get("flags") or {}
    role = "wall"
    if flags.get("targetWall") is True:
        role = "target"
    elif flags.get("stopWall") is True:
        role = "stop"

    return {
        "strike": level.get("strike"),
        "dominantSide": level.get("dominantSide"),
        "position": level.get("position"),
        "role": role,
        "distancePctFromSpot": level.get("distancePctFromSpot"),
        "hybridStrength": level.get("hybridStrength"),
        "sign": level.get("sign"),
        "behavior": level.get("behavior"),
    }


def _build_validation_gex_walls(indicators: dict) -> list:
    gex = indicators.get("gex") or {}
    levels = gex.get("levels") or []
    return [
        _summarize_gex_level_for_validation(level)
        for level in levels
        if isinstance(level, dict)
        and (level.get("flags") or {}).get("wall") is True
    ]


def _sanitize_check_value(name: str, value: Any, indicators: Optional[dict] = None):
    value = _camelize_known(value)

    if name == "gex_order" and isinstance(value, dict):
        target_wall = value.get("targetWall") or {}
        stop_wall = value.get("stopWall") or {}
        return {
            "targetWallStrike": target_wall.get("strike"),
            "targetWallType": target_wall.get("type") or target_wall.get("option_type"),
            "targetWallDominantSide": target_wall.get("dominantSide"),
            "stopWallStrike": stop_wall.get("strike"),
            "stopWallType": stop_wall.get("type") or stop_wall.get("option_type"),
            "stopWallDominantSide": stop_wall.get("dominantSide"),
            "targetMode": value.get("targetMode"),
            "targetSelectionMode": value.get("targetSelectionMode"),
            "walls": _build_validation_gex_walls(indicators or {}),
        }

    return value


def _build_validation(strategy_validation, indicators: Optional[dict] = None) -> dict:
    strategy_validation = strategy_validation if isinstance(strategy_validation, dict) else {}
    checks = strategy_validation.get("checks") or []
    details = [
        {
            "name": check.get("name"),
            "passed": check.get("passed"),
            "reason": check.get("reason"),
            "value": _sanitize_check_value(check.get("name"), check.get("value"), indicators),
        }
        for check in checks
    ]
    failed = [check for check in details if not check.get("passed")]

    return {
        "validator": strategy_validation.get("validator"),
        "decision": strategy_validation.get("decision"),
        "passed": strategy_validation.get("decision") == "VALID",
        "summary": {
            "totalChecks": len(details),
            "passedChecks": len(details) - len(failed),
            "failedChecks": len(failed),
            "failedReasons": [check.get("reason") for check in failed],
        },
        "details": details,
    }


def _build_order_proposal(decision: str, strategy_validation):
    if decision != "VALID" or not isinstance(strategy_validation, dict):
        return None

    order = strategy_validation.get("orderProposal")
    if not isinstance(order, dict):
        return None

    return {
        "entry": order.get("entry"),
        "stopLoss": order.get("stopLoss"),
        "takeProfit": order.get("takeProfit"),
        "targetMode": order.get("targetMode"),
        "targetSelectionMode": order.get("targetSelectionMode"),
        "trailing": order.get("trailing"),
    }


def _build_analyze_response(
    normalized: dict,
    classification,
    market_context,
    strategy_validation,
    decision: str,
    reason: str,
) -> dict:
    market_context = _serialize_market_context(market_context)
    indicators = _build_indicators(market_context, strategy_validation)

    return {
        "decision": decision,
        "reason": reason,
        "received": _build_received(normalized),
        "alertContext": _build_alert_context(normalized, classification),
        "classification": _build_classification(normalized, classification),
        "marketData": _build_market_data(market_context, classification),
        "indicators": indicators,
        "validation": _build_validation(strategy_validation, indicators),
        "orderProposal": _build_order_proposal(decision, strategy_validation),
    }


def analyze_normalized(normalized: dict):
    # TODO: Replace same-market-day guard with max age guard, e.g. alert age <= 10 minutes.
    if not _is_alert_from_market_today(normalized):
        return _rejected_response(normalized, "Alert is not from current US market day")

    classification = classify_alert(normalized)
    market_context = get_market_context(normalized, classification)
    _attach_indicators(normalized, classification, market_context)
    strategy_validation = validate_by_strategy(
        normalized,
        classification,
        market_context=market_context,
        ticker_context=_get_ticker_context(classification)
    )
    final_decision, final_reason = _get_final_decision(strategy_validation)

    return _build_analyze_response(
        normalized=normalized,
        classification=classification,
        market_context=market_context,
        strategy_validation=strategy_validation,
        decision=final_decision,
        reason=final_reason,
    )
