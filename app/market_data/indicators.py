import os
from typing import Optional

from app.market_data.gex import compute_stop_buffer, compute_target_buffer


DEBUG_OPTION_CHAIN = os.getenv("DEBUG_OPTION_CHAIN", "").lower() in ("1", "true", "yes")
MOVE_ESTIMATE_METHOD = "delta_gamma_spread_buffer"
MOVE_ESTIMATE_SAFETY_MULTIPLIER = 1.2
ACCELERATOR_STRENGTH_RATIO = 0.75


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result


def _safe_positive_float(value) -> Optional[float]:
    result = _safe_float(value)
    if result is None or result <= 0:
        return None
    return result


def _get_value(value, key):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _wall_strength(wall) -> float:
    return _safe_float(_get_value(wall, "hybrid_strength")) or 0


def _wall_distance(wall) -> Optional[float]:
    distance = _safe_float(_get_value(wall, "distance_from_spot"))
    return abs(distance) if distance is not None else None


def _behavior_score(behavior, clear_behavior: str) -> float:
    if behavior == clear_behavior:
        return 1.0
    if behavior == "mixed":
        return 0.85
    if behavior == "unknown":
        return 0.75
    return 0.0


def _score_wall(wall, max_strength: float, nearest_distance: float, clear_behavior: str) -> float:
    strength = _wall_strength(wall)
    distance = _wall_distance(wall)

    strength_rank = strength / max_strength if max_strength > 0 else 0
    distance_rank = nearest_distance / distance if distance and distance > 0 else 1
    behavior_rank = _behavior_score(_get_value(wall, "behavior"), clear_behavior)

    return strength_rank * 0.45 + distance_rank * 0.30 + behavior_rank * 0.25


def _get_alert_price(normalized: dict) -> Optional[float]:
    trade = normalized.get("trade") or {}
    alert = normalized.get("alert") or {}

    return (
        _safe_float(trade.get("price"))
        or _safe_float(alert.get("price"))
        or _safe_float(alert.get("alertPrice"))
    )


def _calculate_price_deviation_pct(normalized: dict, market_context: dict) -> Optional[float]:
    option_market = market_context.get("option") or {}

    alert_price = _get_alert_price(normalized)
    current_option_price = _safe_positive_float(option_market.get("ask"))

    if alert_price is None or alert_price == 0 or current_option_price is None:
        return None

    return ((current_option_price - alert_price) / alert_price) * 100


def _calculate_spread(market_context: dict) -> Optional[float]:
    option = market_context.get("option") or {}

    bid = _safe_positive_float(option.get("bid"))
    ask = _safe_positive_float(option.get("ask"))

    if bid is None or ask is None:
        return None

    return ask - bid


def _calculate_mid(market_context: dict) -> Optional[float]:
    option = market_context.get("option") or {}

    bid = _safe_positive_float(option.get("bid"))
    ask = _safe_positive_float(option.get("ask"))

    if bid is None or ask is None:
        return None

    return (bid + ask) / 2


def _calculate_price_deviation(normalized: dict, market_context: dict) -> Optional[float]:
    option_market = market_context.get("option") or {}

    alert_price = _get_alert_price(normalized)
    current_option_price = _safe_positive_float(option_market.get("ask"))

    if alert_price is None or current_option_price is None:
        return None

    return current_option_price - alert_price


def _calculate_spread_pct(market_context: dict) -> Optional[float]:
    option = market_context.get("option") or {}

    bid = _safe_positive_float(option.get("bid"))
    ask = _safe_positive_float(option.get("ask"))

    if bid is None or ask is None:
        return None

    mid = (bid + ask) / 2
    if mid == 0:
        return None

    return ((ask - bid) / mid) * 100


def _get_contract_type(normalized: dict, market_context: dict) -> Optional[str]:
    normalized_option = normalized.get("option") or {}
    market_option = market_context.get("option") or {}

    return normalized_option.get("type") or market_option.get("type")


def _get_gex_context(market_context: dict):
    return market_context.get("gex_context") or market_context.get("gex")


def _get_gex_walls(market_context: dict) -> list:
    gex_context = _get_gex_context(market_context) or {}
    walls = _get_value(gex_context, "walls") or []
    return walls if isinstance(walls, list) else []


def _summarize_exit_level(wall, source: str) -> Optional[dict]:
    if wall is None:
        return None

    strike = _safe_float(_get_value(wall, "strike"))
    if strike is None:
        return None

    return {
        "strike": strike,
        "position": _get_value(wall, "position"),
        "behavior": _get_value(wall, "behavior"),
        "source": source,
        "hybridStrength": _safe_float(_get_value(wall, "hybrid_strength")),
        "signedScore": _safe_float(_get_value(wall, "sign_score")),
    }


def _buffered_stop(alert_side: Optional[str], strike: Optional[float], entry: Optional[float]) -> Optional[float]:
    buffer = compute_stop_buffer(entry)
    if strike is None or buffer is None:
        return None
    if alert_side == "CALL":
        return strike - buffer
    if alert_side == "PUT":
        return strike + buffer
    return None


def _buffered_target(alert_side: Optional[str], strike: Optional[float], entry: Optional[float]) -> Optional[float]:
    buffer = compute_target_buffer(entry)
    if strike is None or buffer is None:
        return None
    if alert_side == "CALL":
        return strike - buffer
    if alert_side == "PUT":
        return strike + buffer
    return None


def _is_executable_stop(alert_side: Optional[str], entry: Optional[float], stop: Optional[float]) -> bool:
    if entry is None or stop is None:
        return False
    if alert_side == "CALL":
        return stop < entry
    if alert_side == "PUT":
        return stop > entry
    return False


def _is_executable_target(alert_side: Optional[str], entry: Optional[float], target: Optional[float]) -> bool:
    if entry is None or target is None:
        return False
    if alert_side == "CALL":
        return target > entry
    if alert_side == "PUT":
        return target < entry
    return False


def _select_scored_wall(walls: list, position: str, behaviors: tuple, clear_behavior: str):
    candidates = [
        wall for wall in walls
        if _get_value(wall, "position") == position
        and _get_value(wall, "behavior") in behaviors
        and _wall_strength(wall) > 0
    ]
    if not candidates:
        return None

    max_strength = max(_wall_strength(wall) for wall in candidates) or 1
    distances = [
        _wall_distance(wall)
        for wall in candidates
        if _wall_distance(wall) is not None and _wall_distance(wall) > 0
    ]
    nearest_distance = min(distances) if distances else 1

    return max(
        candidates,
        key=lambda wall: _score_wall(wall, max_strength, nearest_distance, clear_behavior)
    )


def _select_stop(walls: list, alert_side: Optional[str], entry: Optional[float]):
    if alert_side == "CALL":
        position = "below"
        behaviors = ("support", "mixed", "unknown")
        clear_behavior = "support"
    elif alert_side == "PUT":
        position = "above"
        behaviors = ("resistance", "mixed", "unknown")
        clear_behavior = "resistance"
    else:
        return None, None

    executable = []
    for wall in walls:
        if _get_value(wall, "position") != position:
            continue
        if _get_value(wall, "behavior") not in behaviors:
            continue
        if _wall_strength(wall) <= 0:
            continue

        strike = _safe_float(_get_value(wall, "strike"))
        stop = _buffered_stop(alert_side, strike, entry)
        if _is_executable_stop(alert_side, entry, stop):
            executable.append(wall)

    wall = _select_scored_wall(executable, position, behaviors, clear_behavior)
    if wall is None:
        return None, None

    strike = _safe_float(_get_value(wall, "strike"))
    return wall, _buffered_stop(alert_side, strike, entry)


def _select_target(walls: list, alert_side: Optional[str], entry: Optional[float]):
    if alert_side == "CALL":
        position = "above"
        behaviors = ("resistance", "mixed", "unknown")
        clear_behavior = "resistance"
    elif alert_side == "PUT":
        position = "below"
        behaviors = ("support", "mixed", "unknown")
        clear_behavior = "support"
    else:
        return None, None

    executable = []
    for wall in walls:
        if _get_value(wall, "position") != position:
            continue
        if _get_value(wall, "behavior") not in behaviors:
            continue
        if _wall_strength(wall) <= 0:
            continue

        strike = _safe_float(_get_value(wall, "strike"))
        target = _buffered_target(alert_side, strike, entry)
        if _is_executable_target(alert_side, entry, target):
            executable.append(wall)

    wall = _select_scored_wall(executable, position, behaviors, clear_behavior)
    if wall is None:
        return None, None

    strike = _safe_float(_get_value(wall, "strike"))
    return wall, _buffered_target(alert_side, strike, entry)


def _select_trigger(walls: list, alert_side: Optional[str], target_wall):
    if alert_side == "CALL":
        position = "above"
        behavior = "breakout_accelerator"
        direction = "up"
    elif alert_side == "PUT":
        position = "below"
        behavior = "breakdown_accelerator"
        direction = "down"
    else:
        return None

    accelerators = [
        wall for wall in walls
        if _get_value(wall, "position") == position
        and _get_value(wall, "behavior") == behavior
        and _wall_strength(wall) > 0
    ]
    if not accelerators:
        return None

    strongest_accelerator = max(accelerators, key=_wall_strength)
    target_strength = _wall_strength(target_wall) if target_wall is not None else 0

    if target_strength > 0 and _wall_strength(strongest_accelerator) < target_strength * ACCELERATOR_STRENGTH_RATIO:
        return None

    trigger = _summarize_exit_level(
        strongest_accelerator,
        "gex_context.directional_accelerator"
    )
    if trigger is None:
        return None

    trigger["trailing"] = {
        "enabled": True,
        "mode": "diagnostic_only",
        "activationLevel": trigger.get("strike"),
        "direction": direction,
    }
    return trigger


def _get_selected_exit_levels(normalized: dict, market_context: dict) -> dict:
    walls = _get_gex_walls(market_context)
    if not walls:
        return {
            "stop": None,
            "target": None,
            "trigger": None,
        }

    contract_type = _get_contract_type(normalized, market_context)
    underlying = market_context.get("underlying") or {}
    entry = _safe_float(underlying.get("price"))

    stop_wall, stop_price = _select_stop(walls, contract_type, entry)
    target_wall, target_price = _select_target(walls, contract_type, entry)

    stop = _summarize_exit_level(stop_wall, "gex_context.scored_buffered_stop")
    target = _summarize_exit_level(target_wall, "gex_context.scored_buffered_target")
    trigger = _select_trigger(walls, contract_type, target_wall)

    if stop is not None:
        stop["triggerPrice"] = stop_price
    if target is not None:
        target["triggerPrice"] = target_price

    return {
        "stop": stop,
        "target": target,
        "trigger": trigger,
    }


def _get_underlying_indicators(market_context: dict, selected_exit_levels: dict) -> dict:
    underlying = market_context.get("underlying") or {}

    selected_stop = selected_exit_levels.get("stop") or {}
    selected_target = selected_exit_levels.get("target") or {}

    entry = _safe_float(underlying.get("price"))
    stop = _safe_float(selected_stop.get("triggerPrice") or selected_stop.get("strike"))
    target = _safe_float(selected_target.get("triggerPrice") or selected_target.get("strike"))

    stop_distance = abs(entry - stop) if entry is not None and stop is not None else None
    target_distance = abs(target - entry) if entry is not None and target is not None else None
    risk_pct = (stop_distance / entry * 100) if entry and stop_distance is not None else None
    reward_pct = (target_distance / entry * 100) if entry and target_distance is not None else None
    risk_reward = (
        target_distance / stop_distance
        if stop_distance is not None and stop_distance > 0 and target_distance is not None
        else None
    )

    return {
        "entry": entry,
        "stop": stop,
        "target": target,
        "stopDistance": stop_distance,
        "targetDistance": target_distance,
        "riskPct": risk_pct,
        "rewardPct": reward_pct,
        "riskReward": risk_reward,
    }


def _get_option_price_indicators(normalized: dict, market_context: dict) -> dict:
    option = market_context.get("option") or {}

    return {
        "bid": _safe_positive_float(option.get("bid")),
        "ask": _safe_positive_float(option.get("ask")),
        "last": _safe_float(option.get("last")),
        "mid": _calculate_mid(market_context),
        "alertPrice": _get_alert_price(normalized),
        "priceDeviation": _calculate_price_deviation(normalized, market_context),
        "priceDeviationPct": _calculate_price_deviation_pct(normalized, market_context),
        "spread": _calculate_spread(market_context),
        "spreadPct": _calculate_spread_pct(market_context),
    }


def _get_option_liquidity_indicators(market_context: dict) -> dict:
    option = market_context.get("option") or {}

    return {
        "volume": _safe_float(option.get("volume")),
        "openInterest": _safe_float(option.get("open_interest") or option.get("openInterest")),
    }


def _get_option_greeks(market_context: dict) -> dict:
    option = market_context.get("option") or {}

    return {
        "delta": _safe_float(option.get("delta")),
        "gamma": _safe_float(option.get("gamma")),
        "theta": _safe_float(option.get("theta")),
        "vega": _safe_float(option.get("vega")),
        "rho": _safe_float(option.get("rho")),
        "iv": _safe_float(option.get("iv") or option.get("implied_volatility")),
    }


def _get_move_estimates(underlying: dict, option_price: dict, greeks: dict):
    delta = _safe_float(greeks.get("delta"))
    gamma = _safe_float(greeks.get("gamma"))
    bid = _safe_positive_float(option_price.get("bid"))
    ask = _safe_positive_float(option_price.get("ask"))
    entry = _safe_float(underlying.get("entry"))
    stop = _safe_float(underlying.get("stop"))
    target = _safe_float(underlying.get("target"))

    if None in (delta, gamma, bid, ask, entry, stop, target):
        return None

    stop_distance = abs(entry - stop)
    target_distance = abs(target - entry)
    spread = ask - bid

    estimated_loss = (
        abs(delta) * stop_distance
        + 0.5 * abs(gamma) * stop_distance ** 2
        + spread * 0.5
    ) * MOVE_ESTIMATE_SAFETY_MULTIPLIER

    estimated_gain = (
        abs(delta) * target_distance
        + 0.5 * abs(gamma) * target_distance ** 2
        - spread * 0.5
    )

    estimated_loss_per_contract = estimated_loss * 100
    estimated_reward_per_contract = estimated_gain * 100

    return {
        "method": MOVE_ESTIMATE_METHOD,
        "safetyMultiplier": MOVE_ESTIMATE_SAFETY_MULTIPLIER,
        "estimatedOptionLossToStop": estimated_loss,
        "estimatedOptionGainToTarget": estimated_gain,
        "estimatedOptionPriceAtStop": max(0.01, ask - estimated_loss),
        "estimatedOptionPriceAtTarget": max(0.01, ask + estimated_gain),
        "estimatedLossPerContract": estimated_loss_per_contract,
        "estimatedRewardPerContract": estimated_reward_per_contract,
        "estimatedRiskReward": (
            estimated_reward_per_contract / estimated_loss_per_contract
            if estimated_loss_per_contract > 0
            else None
        ),
    }


def _same_level(level: dict, selected_level: Optional[dict]) -> bool:
    if not selected_level:
        return False

    return (
        _safe_float(level.get("strike")) == _safe_float(selected_level.get("strike"))
        and level.get("position") == selected_level.get("position")
        and level.get("behavior") == selected_level.get("behavior")
    )


def _get_significant_levels(market_context: dict, selected_exit_levels: dict) -> list:
    gex_context = _get_gex_context(market_context) or {}
    walls = _get_value(gex_context, "walls") or []
    if not isinstance(walls, list):
        return []

    levels = []
    selected_stop = selected_exit_levels.get("stop")
    selected_target = selected_exit_levels.get("target")

    for wall in walls:
        level = {
            "strike": _get_value(wall, "strike"),
            "type": _get_value(wall, "type"),
            "position": _get_value(wall, "position"),
            "behavior": _get_value(wall, "behavior"),
            "role": _get_value(wall, "role"),
            "hybridStrength": _get_value(wall, "hybrid_strength"),
            "signedScore": _get_value(wall, "sign_score"),
        }

        if _same_level(level, selected_stop):
            level["role"] = "selected_stop"
        elif _same_level(level, selected_target):
            level["role"] = "selected_target"

        levels.append(level)

    return levels


def calculate_indicators(normalized: dict, market_context: dict) -> dict:
    selected_exit_levels = _get_selected_exit_levels(normalized, market_context)
    underlying = _get_underlying_indicators(market_context, selected_exit_levels)
    option_price = _get_option_price_indicators(normalized, market_context)
    option_liquidity = _get_option_liquidity_indicators(market_context)
    option_greeks = _get_option_greeks(market_context)

    return {
        "selectedExitLevels": selected_exit_levels,
        "underlying": underlying,
        "option": {
            "price": option_price,
            "liquidity": option_liquidity,
            "greeks": option_greeks,
            "moveEstimates": _get_move_estimates(
                underlying,
                option_price,
                option_greeks
            ),
        },
        "significantLevels": _get_significant_levels(market_context, selected_exit_levels),
    }


def calculate_historical_volatility(*args, **kwargs) -> Optional[float]:
    return None


def calculate_iv_hv_ratio(*args, **kwargs) -> Optional[float]:
    return None
