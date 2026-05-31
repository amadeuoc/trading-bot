import os
from typing import Optional


DEBUG_OPTION_CHAIN = os.getenv("DEBUG_OPTION_CHAIN", "").lower() in ("1", "true", "yes")
MOVE_ESTIMATE_METHOD = "delta_gamma_spread_buffer"
MOVE_ESTIMATE_SAFETY_MULTIPLIER = 1.2


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


def _get_underlying_indicators(market_context: dict) -> dict:
    underlying = market_context.get("underlying") or {}
    trade_plan = market_context.get("trade_plan") or {}

    entry = _safe_float(trade_plan.get("entry") or underlying.get("price"))
    stop = _safe_float(trade_plan.get("stop"))
    target = _safe_float(trade_plan.get("target"))

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


def _get_significant_levels(market_context: dict) -> list:
    gex_context = market_context.get("gex_context") or {}
    if not isinstance(gex_context, dict):
        return []

    levels = []
    for wall in gex_context.get("walls") or []:
        if not isinstance(wall, dict):
            continue

        levels.append({
            "strike": wall.get("strike"),
            "type": wall.get("type"),
            "position": wall.get("position"),
            "behavior": wall.get("behavior"),
            "role": wall.get("role"),
            "hybridStrength": wall.get("hybrid_strength"),
            "signedScore": wall.get("sign_score"),
        })

    return levels


def calculate_indicators(normalized: dict, market_context: dict) -> dict:
    underlying = _get_underlying_indicators(market_context)
    option_price = _get_option_price_indicators(normalized, market_context)
    option_liquidity = _get_option_liquidity_indicators(market_context)
    option_greeks = _get_option_greeks(market_context)

    return {
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
        "significantLevels": _get_significant_levels(market_context),
    }


def calculate_historical_volatility(*args, **kwargs) -> Optional[float]:
    return None


def calculate_iv_hv_ratio(*args, **kwargs) -> Optional[float]:
    return None
