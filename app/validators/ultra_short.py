import math
from typing import Any, Optional

from app.market_data.gex import compute_stop_buffer, compute_target_buffer


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result) or math.isinf(result):
        return None

    return result


def _get_classification_value(classification: Any, key: str):
    if isinstance(classification, dict):
        return classification.get(key)
    return getattr(classification, key, None)


def _add_check(checks: list, name: str, passed: bool, reason: str, value: Any):
    check = {
        "name": name,
        "passed": passed,
        "reason": reason,
        "value": value
    }
    checks.append(check)
    return check


def _empty_risk_reward() -> dict:
    return {
        "entry": None,
        "stop": None,
        "target": None,
        "risk": None,
        "reward": None,
        "risk_reward": None
    }


def _get_value(source, key):
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _wall_to_dict(wall):
    if wall is None:
        return None
    if isinstance(wall, dict):
        return wall
    if hasattr(wall, "model_dump"):
        return wall.model_dump()
    return wall


def _empty_gex_order(spot=None, reason="No GEX context available"):
    return {
        "entry": spot,
        "stopLoss": None,
        "takeProfit": None,
        "targetMode": "unknown",
        "trailing": {
            "enabled": False,
            "activationLevel": None,
            "direction": None
        },
        "gexReason": reason,
        "gexWalls": {
            "targetWall": None,
            "stopWall": None
        },
        "checks": []
    }


def _add_gex_order_check(order, passed: bool, reason: str, value: Any = None):
    order["checks"].append({
        "name": "gex_order",
        "passed": passed,
        "reason": reason,
        "value": value
    })


def _validate_gex_order_sides(order, alert_side, spot):
    if alert_side == "CALL":
        if order["takeProfit"] is not None and order["takeProfit"] <= spot:
            _add_gex_order_check(order, False, "CALL takeProfit must be above entry", order["takeProfit"])
            order["takeProfit"] = None
        if order["stopLoss"] is not None and order["stopLoss"] >= spot:
            _add_gex_order_check(order, False, "CALL stopLoss must be below entry", order["stopLoss"])
            order["stopLoss"] = None

    if alert_side == "PUT":
        if order["takeProfit"] is not None and order["takeProfit"] >= spot:
            _add_gex_order_check(order, False, "PUT takeProfit must be below entry", order["takeProfit"])
            order["takeProfit"] = None
        if order["stopLoss"] is not None and order["stopLoss"] <= spot:
            _add_gex_order_check(order, False, "PUT stopLoss must be above entry", order["stopLoss"])
            order["stopLoss"] = None


def build_ultra_short_gex_order(alert_side, spot, gex_context):
    spot = _safe_float(spot)
    if spot is None or spot <= 0:
        return _empty_gex_order(spot, "Cannot build GEX order without valid spot")

    if gex_context is None:
        return _empty_gex_order(spot)

    target_buffer = compute_target_buffer(spot)
    stop_buffer = compute_stop_buffer(spot)
    nearest_above = _get_value(gex_context, "nearest_wall_above")
    nearest_below = _get_value(gex_context, "nearest_wall_below")

    order = _empty_gex_order(spot, "GEX order built from nearest walls")

    if alert_side == "CALL":
        target_wall = nearest_above
        stop_wall = nearest_below
        order["gexWalls"]["targetWall"] = _wall_to_dict(target_wall)
        order["gexWalls"]["stopWall"] = _wall_to_dict(stop_wall)

        if target_wall is None:
            _add_gex_order_check(order, True, "No nearest wall above for CALL target")
        elif _get_value(target_wall, "sign") == "negative":
            order["targetMode"] = "none_trailing_after_wall"
            order["trailing"] = {
                "enabled": True,
                "activationLevel": _get_value(target_wall, "strike"),
                "direction": "up"
            }
        else:
            order["targetMode"] = "fixed"
            order["takeProfit"] = _get_value(target_wall, "strike") - target_buffer

        if stop_wall is None:
            _add_gex_order_check(order, True, "No nearest wall below for CALL stop")
        elif _get_value(stop_wall, "sign") == "negative":
            order["stopLoss"] = _get_value(stop_wall, "strike") + stop_buffer
        else:
            order["stopLoss"] = _get_value(stop_wall, "strike") - stop_buffer

    elif alert_side == "PUT":
        target_wall = nearest_below
        stop_wall = nearest_above
        order["gexWalls"]["targetWall"] = _wall_to_dict(target_wall)
        order["gexWalls"]["stopWall"] = _wall_to_dict(stop_wall)

        if target_wall is None:
            _add_gex_order_check(order, True, "No nearest wall below for PUT target")
        elif _get_value(target_wall, "sign") == "negative":
            order["targetMode"] = "none_trailing_after_wall"
            order["trailing"] = {
                "enabled": True,
                "activationLevel": _get_value(target_wall, "strike"),
                "direction": "down"
            }
        else:
            order["targetMode"] = "fixed"
            order["takeProfit"] = _get_value(target_wall, "strike") + target_buffer

        if stop_wall is None:
            _add_gex_order_check(order, True, "No nearest wall above for PUT stop")
        elif _get_value(stop_wall, "sign") == "negative":
            order["stopLoss"] = _get_value(stop_wall, "strike") - stop_buffer
        else:
            order["stopLoss"] = _get_value(stop_wall, "strike") + stop_buffer

    else:
        order["gexReason"] = "Unknown alert side for GEX order"
        _add_gex_order_check(order, False, "Unknown alert side", alert_side)
        return order

    _validate_gex_order_sides(order, alert_side, spot)
    return order


def _calculate_risk_reward(classification: Any, market_context: dict) -> tuple:
    underlying = market_context.get("underlying") or {}
    indicators = market_context.get("indicators") or {}

    entry = _safe_float(underlying.get("price"))
    support = _safe_float(indicators.get("pseudo_gex_support"))
    resistance = _safe_float(indicators.get("pseudo_gex_resistance"))
    sentiment = _get_classification_value(classification, "sentiment")

    risk_reward = _empty_risk_reward()
    risk_reward["entry"] = entry

    if sentiment == "bullish":
        risk_reward["stop"] = support
        risk_reward["target"] = resistance

        if support is None:
            return risk_reward, False, "Missing pseudo-GEX support from Open Interest"
        if entry is None:
            return risk_reward, False, "Missing underlying entry price"
        if resistance is None:
            return risk_reward, True, "No pseudo-GEX resistance above"

        risk = entry - support
        reward = resistance - entry

    elif sentiment == "bearish":
        risk_reward["stop"] = resistance
        risk_reward["target"] = support

        if resistance is None:
            return risk_reward, False, "Missing pseudo-GEX resistance from Open Interest"
        if entry is None:
            return risk_reward, False, "Missing underlying entry price"
        if support is None:
            return risk_reward, True, "No pseudo-GEX support below"

        risk = resistance - entry
        reward = entry - support

    else:
        return risk_reward, False, "Neutral or unknown sentiment"

    risk_reward["risk"] = risk
    risk_reward["reward"] = reward

    if risk <= 0 or reward <= 0:
        return risk_reward, False, "Invalid risk/reward geometry"

    risk_reward["risk_reward"] = reward / risk
    if risk_reward["risk_reward"] > 2:
        return risk_reward, True, "Risk/reward is acceptable"

    return risk_reward, False, "Risk/reward must be greater than 2"


def validate_ultra_short(
    normalized: dict,
    classification: Any,
    market_context: Any = None,
    ticker_context: Any = None
) -> dict:
    market_context = market_context if isinstance(market_context, dict) else {}
    option_market = market_context.get("option") or {}
    indicators = market_context.get("indicators") or {}
    gex_context = market_context.get("gex_context") or market_context.get("gex")

    checks = []

    price_deviation_pct = _safe_float(indicators.get("price_deviation_pct"))
    price_passed = price_deviation_pct is not None and price_deviation_pct <= 5
    _add_check(
        checks,
        "price",
        price_passed,
        "Price deviation is acceptable" if price_passed else "Price deviation is missing or above 5%",
        price_deviation_pct
    )

    bid = _safe_float(option_market.get("bid"))
    ask = _safe_float(option_market.get("ask"))
    volume = _safe_float(option_market.get("volume"))
    liquidity_failures = []
    if bid is None or bid <= 0:
        liquidity_failures.append("bid must be greater than 0")
    if ask is None or ask <= 0:
        liquidity_failures.append("ask must be greater than 0")
    if volume is None or volume < 100:
        liquidity_failures.append("volume must be at least 100")

    _add_check(
        checks,
        "liquidity",
        not liquidity_failures,
        "Liquidity is acceptable" if not liquidity_failures else "; ".join(liquidity_failures),
        {
            "bid": bid,
            "ask": ask,
            "volume": volume
        }
    )

    spread_pct = _safe_float(indicators.get("spread_pct"))
    spread_failures = []
    if spread_pct is None:
        spread_failures.append("spread_pct is missing")
    elif spread_pct > 10:
        spread_failures.append("spread_pct is above 10%")

    _add_check(
        checks,
        "spread",
        not spread_failures,
        "Spread is acceptable" if not spread_failures else "; ".join(spread_failures),
        {
            "spread_pct": spread_pct
        }
    )

    risk_reward, risk_reward_passed, risk_reward_reason = _calculate_risk_reward(
        classification,
        market_context
    )
    _add_check(
        checks,
        "risk_reward",
        risk_reward_passed,
        risk_reward_reason,
        risk_reward
    )

    order_proposal = None
    if gex_context is not None:
        underlying = market_context.get("underlying") or {}
        option = normalized.get("option") or {}
        order_proposal = build_ultra_short_gex_order(
            option.get("type"),
            underlying.get("price"),
            gex_context
        )
        gex_summary = {
            "nearest_wall_above": _wall_to_dict(_get_value(gex_context, "nearest_wall_above")),
            "nearest_wall_below": _wall_to_dict(_get_value(gex_context, "nearest_wall_below")),
            "strongest_wall_above": _wall_to_dict(_get_value(gex_context, "strongest_wall_above")),
            "strongest_wall_below": _wall_to_dict(_get_value(gex_context, "strongest_wall_below")),
            "strongest_call_wall": _wall_to_dict(_get_value(gex_context, "strongest_call_wall")),
            "strongest_put_wall": _wall_to_dict(_get_value(gex_context, "strongest_put_wall")),
            "targetMode": order_proposal.get("targetMode"),
            "trailing.enabled": order_proposal.get("trailing", {}).get("enabled"),
            "trailing.activationLevel": order_proposal.get("trailing", {}).get("activationLevel"),
            "stopLoss": order_proposal.get("stopLoss"),
            "takeProfit": order_proposal.get("takeProfit"),
            "gexReason": order_proposal.get("gexReason")
        }
        _add_check(
            checks,
            "gex_order",
            True,
            "GEX order context attached",
            gex_summary
        )

    failed_checks = [check for check in checks if not check["passed"]]
    decision = "VALID" if not failed_checks else "REJECT"
    reason = "Ultra short validation passed"

    if decision == "REJECT":
        failed_reasons = [check["reason"] for check in failed_checks]
        reason = "Ultra short validation failed: " + "; ".join(failed_reasons)

    return {
        "validator": "ultra_short",
        "decision": decision,
        "reason": reason,
        "checks": checks,
        "failedChecks": failed_checks,
        "riskReward": risk_reward,
        "orderProposal": order_proposal
    }
