import math
from typing import Any, Optional


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
        "orderProposal": None
    }
