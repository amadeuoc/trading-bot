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


def _get_walls(gex_context):
    walls = _get_value(gex_context, "walls") or []
    return walls if isinstance(walls, list) else []


def _wall_strength(wall):
    return _safe_float(_get_value(wall, "hybrid_strength")) or 0


def _wall_distance(wall):
    return abs(_safe_float(_get_value(wall, "distance_from_spot")) or 0)


def _filter_trade_walls(gex_context, position, behavior):
    return [
        wall for wall in _get_walls(gex_context)
        if _get_value(wall, "position") == position
        and _get_value(wall, "behavior") == behavior
        and _wall_strength(wall) > 0
    ]


def _select_nearest_trade_wall(gex_context, position, behavior):
    walls = _filter_trade_walls(gex_context, position, behavior)
    return min(walls, key=_wall_distance) if walls else None


def _target_candidates_by_proximity(gex_context, position, behavior):
    return sorted(
        _filter_trade_walls(gex_context, position, behavior),
        key=_wall_distance
    )


def _calculate_candidate_target(alert_side, target_wall, target_buffer):
    strike = _safe_float(_get_value(target_wall, "strike"))
    if strike is None or target_buffer is None:
        return None

    if alert_side == "CALL":
        return strike - target_buffer
    if alert_side == "PUT":
        return strike + target_buffer
    return None


def _is_executable_target(alert_side, entry, target):
    entry = _safe_float(entry)
    target = _safe_float(target)

    if entry is None or target is None:
        return False
    if alert_side == "CALL":
        return target > entry
    if alert_side == "PUT":
        return target < entry
    return False


def _select_nearest_executable_target_wall(
    gex_context,
    alert_side,
    entry,
    target_buffer,
    position,
    behavior
):
    rejected = []

    for wall in _target_candidates_by_proximity(gex_context, position, behavior):
        target = _calculate_candidate_target(alert_side, wall, target_buffer)
        if _is_executable_target(alert_side, entry, target):
            return wall, target, rejected

        rejected.append({
            "strike": _get_value(wall, "strike"),
            "target": target,
            "reason": "Target is not executable after buffer"
        })

    return None, None, rejected


def _empty_gex_trade_plan(spot=None, reason="No GEX context available"):
    return {
        "entry": spot,
        "stop": None,
        "target": None,
        "targetMode": "unknown",
        "targetSelectionMode": "unknown",
        "trailing": {
            "enabled": False,
            "activationLevel": None,
            "direction": None
        },
        "reason": reason,
        "targetWall": None,
        "stopWall": None,
        "targetSelection": {
            "rejectedCandidates": []
        },
        "checks": []
    }


def _add_gex_trade_plan_check(trade_plan, passed: bool, reason: str, value: Any = None):
    trade_plan["checks"].append({
        "name": "gex_order",
        "passed": passed,
        "reason": reason,
        "value": value
    })


def _validate_gex_trade_plan_sides(trade_plan, alert_side, spot):
    if alert_side == "CALL":
        if trade_plan["target"] is not None and trade_plan["target"] <= spot:
            _add_gex_trade_plan_check(trade_plan, False, "CALL takeProfit must be above entry", trade_plan["target"])
            trade_plan["target"] = None
        if trade_plan["stop"] is not None and trade_plan["stop"] >= spot:
            _add_gex_trade_plan_check(trade_plan, False, "CALL stopLoss must be below entry", trade_plan["stop"])
            trade_plan["stop"] = None

    if alert_side == "PUT":
        if trade_plan["target"] is not None and trade_plan["target"] >= spot:
            _add_gex_trade_plan_check(trade_plan, False, "PUT takeProfit must be below entry", trade_plan["target"])
            trade_plan["target"] = None
        if trade_plan["stop"] is not None and trade_plan["stop"] <= spot:
            _add_gex_trade_plan_check(trade_plan, False, "PUT stopLoss must be above entry", trade_plan["stop"])
            trade_plan["stop"] = None


def build_ultra_short_gex_trade_plan(alert_side, spot, gex_context):
    spot = _safe_float(spot)
    if spot is None or spot <= 0:
        return _empty_gex_trade_plan(spot, "Cannot build GEX order without valid spot")

    if gex_context is None:
        return _empty_gex_trade_plan(spot)

    target_buffer = compute_target_buffer(spot)
    stop_buffer = compute_stop_buffer(spot)

    trade_plan = _empty_gex_trade_plan(spot, "GEX order built from nearest executable trade walls")
    trade_plan["targetSelectionMode"] = "nearest_executable"

    if alert_side == "CALL":
        stop_wall = _select_nearest_trade_wall(gex_context, "below", "support")
        trade_plan["stopWall"] = _wall_to_dict(stop_wall)

        if stop_wall is None:
            _add_gex_trade_plan_check(trade_plan, False, "No valid defensive support below for CALL stop")
        else:
            trade_plan["stop"] = _get_value(stop_wall, "strike") - stop_buffer

        target_wall, target, rejected = _select_nearest_executable_target_wall(
            gex_context,
            alert_side,
            spot,
            target_buffer,
            "above",
            "resistance"
        )
        trade_plan["targetSelection"]["rejectedCandidates"] = rejected
        trade_plan["targetWall"] = _wall_to_dict(target_wall)
        if target_wall is None:
            _add_gex_trade_plan_check(
                trade_plan,
                False,
                "No executable GEX target wall after buffer checks",
                {"rejectedCandidates": rejected}
            )
        else:
            trade_plan["targetMode"] = "fixed"
            trade_plan["target"] = target

    elif alert_side == "PUT":
        stop_wall = _select_nearest_trade_wall(gex_context, "above", "resistance")
        trade_plan["stopWall"] = _wall_to_dict(stop_wall)

        if stop_wall is None:
            _add_gex_trade_plan_check(trade_plan, False, "No valid defensive resistance above for PUT stop")
        else:
            trade_plan["stop"] = _get_value(stop_wall, "strike") + stop_buffer

        target_wall, target, rejected = _select_nearest_executable_target_wall(
            gex_context,
            alert_side,
            spot,
            target_buffer,
            "below",
            "support"
        )
        trade_plan["targetSelection"]["rejectedCandidates"] = rejected
        trade_plan["targetWall"] = _wall_to_dict(target_wall)
        if target_wall is None:
            _add_gex_trade_plan_check(
                trade_plan,
                False,
                "No executable GEX target wall after buffer checks",
                {"rejectedCandidates": rejected}
            )
        else:
            trade_plan["targetMode"] = "fixed"
            trade_plan["target"] = target

    else:
        trade_plan["reason"] = "Unknown alert side for GEX order"
        _add_gex_trade_plan_check(trade_plan, False, "Unknown alert side", alert_side)
        return trade_plan

    _validate_gex_trade_plan_sides(trade_plan, alert_side, spot)
    return trade_plan


def build_ultra_short_gex_order_from_trade_plan(trade_plan) -> dict:
    trade_plan = trade_plan or _empty_gex_trade_plan()
    return {
        "entry": trade_plan.get("entry"),
        "stopLoss": trade_plan.get("stop"),
        "takeProfit": trade_plan.get("target"),
        "targetMode": trade_plan.get("targetMode"),
        "targetSelectionMode": trade_plan.get("targetSelectionMode"),
        "trailing": trade_plan.get("trailing"),
        "gexReason": trade_plan.get("reason"),
        "gexWalls": {
            "targetWall": trade_plan.get("targetWall"),
            "stopWall": trade_plan.get("stopWall")
        },
        "checks": trade_plan.get("checks", [])
    }


def build_ultra_short_gex_order(alert_side, spot, gex_context):
    trade_plan = build_ultra_short_gex_trade_plan(alert_side, spot, gex_context)
    return build_ultra_short_gex_order_from_trade_plan(trade_plan)


def _calculate_risk_reward(alert_side, trade_plan: Optional[dict] = None) -> tuple:
    risk_reward = _empty_risk_reward()
    risk_reward["source"] = "gex_trade_plan"

    if trade_plan is None:
        return risk_reward, False, "Missing GEX trade plan"

    entry = _safe_float(trade_plan.get("entry"))
    stop = _safe_float(trade_plan.get("stop"))
    target = _safe_float(trade_plan.get("target"))
    target_source = "target"

    if target is None:
        trailing = trade_plan.get("trailing") or {}
        if trailing.get("enabled") is True:
            target = _safe_float(trailing.get("activationLevel"))
            target_source = "trailing_activation"

    risk_reward.update({
        "entry": entry,
        "stop": stop,
        "target": target,
        "target_source": target_source
    })

    if entry is None or stop is None or target is None:
        return (
            risk_reward,
            False,
            "Cannot calculate GEX risk/reward because entry, stop or target/trailing activation is missing"
        )

    if alert_side == "CALL":
        risk = entry - stop
        reward = target - entry
    elif alert_side == "PUT":
        risk = stop - entry
        reward = entry - target
    else:
        return risk_reward, False, "Unknown alert side for GEX risk/reward"

    risk_reward["risk"] = risk
    risk_reward["reward"] = reward

    if risk <= 0 or reward <= 0:
        return risk_reward, False, "Invalid GEX risk/reward geometry"

    risk_reward["risk_reward"] = reward / risk
    if risk_reward["risk_reward"] > 2:
        return risk_reward, True, "GEX risk/reward is acceptable"

    return risk_reward, False, "GEX risk/reward is below minimum"


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

    alert_side = (normalized.get("option") or {}).get("type")
    trade_plan = None
    order_proposal = None
    if gex_context is not None:
        underlying = market_context.get("underlying") or {}
        trade_plan = build_ultra_short_gex_trade_plan(
            alert_side,
            underlying.get("price"),
            gex_context
        )
        order_proposal = build_ultra_short_gex_order_from_trade_plan(trade_plan)
        gex_summary = {
            "targetWall": order_proposal.get("gexWalls", {}).get("targetWall"),
            "stopWall": order_proposal.get("gexWalls", {}).get("stopWall"),
            "strongest_wall_above": _wall_to_dict(_get_value(gex_context, "strongest_wall_above")),
            "strongest_wall_below": _wall_to_dict(_get_value(gex_context, "strongest_wall_below")),
            "strongest_call_wall": _wall_to_dict(_get_value(gex_context, "strongest_call_wall")),
            "strongest_put_wall": _wall_to_dict(_get_value(gex_context, "strongest_put_wall")),
            "targetMode": order_proposal.get("targetMode"),
            "targetSelectionMode": order_proposal.get("targetSelectionMode"),
            "trailing.enabled": order_proposal.get("trailing", {}).get("enabled"),
            "trailing.activationLevel": order_proposal.get("trailing", {}).get("activationLevel"),
            "stopLoss": order_proposal.get("stopLoss"),
            "takeProfit": order_proposal.get("takeProfit"),
            "gexReason": order_proposal.get("gexReason")
        }
        failed_plan_checks = [
            check for check in trade_plan.get("checks", [])
            if not check.get("passed")
        ]
        _add_check(
            checks,
            "gex_order",
            not failed_plan_checks,
            "GEX order context attached" if not failed_plan_checks else failed_plan_checks[0].get("reason"),
            gex_summary
        )

    risk_reward, risk_reward_passed, risk_reward_reason = _calculate_risk_reward(
        alert_side,
        trade_plan
    )
    _add_check(
        checks,
        "risk_reward",
        risk_reward_passed,
        risk_reward_reason,
        risk_reward
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
