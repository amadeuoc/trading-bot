from typing import Any, Dict, Optional


PRICE_DEVIATION_THRESHOLD_PCT = 5
MIN_VOLUME = 100
MAX_SPREAD_PCT = 10
MIN_RISK_REWARD = 2


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check(validation: bool, **values) -> Dict[str, Any]:
    return {
        "validation": validation,
        **values,
    }


def _strategy(classification: Dict[str, Any]) -> Optional[str]:
    return classification.get("strategy") if isinstance(classification, dict) else None


def validate_alert_contract(
    normalized_alert: Dict[str, Any],
    classification: Dict[str, Any],
    indicators: Dict[str, Any],
) -> Dict[str, Any]:
    strategy = _strategy(classification)
    if strategy != "ultra_short":
        reason = f"Strategy not implemented yet: {strategy}"
        return {
            "status": "ok",
            "decision": "SKIP",
            "reason": reason,
            "checks": {
                "strategyImplemented": _check(
                    False,
                    strategy=strategy,
                    reason=reason,
                )
            },
        }

    option = indicators.get("option") or {}
    option_price = option.get("price") or {}
    option_liquidity = option.get("liquidity") or {}
    move_estimates = option.get("moveEstimates") or {}
    underlying = indicators.get("underlying") or {}
    trade = normalized_alert.get("trade") or {}
    alert_price = _safe_float(trade.get("price"))
    current_price = _safe_float(option_price.get("ask"))
    bid = _safe_float(option_price.get("bid"))
    ask = _safe_float(option_price.get("ask"))
    volume = _safe_float(option_liquidity.get("volume"))
    spread_pct = _safe_float(option_price.get("spreadPct"))
    spread_abs = _safe_float(option_price.get("spread"))
    deviation_pct = _safe_float(option_price.get("priceDeviationPct"))
    risk_reward = _safe_float(move_estimates.get("estimatedRiskReward"))
    entry = _safe_float(underlying.get("entry"))
    stop = _safe_float(underlying.get("stop"))
    target = _safe_float(underlying.get("target"))

    checks = {
        "strategyImplemented": _check(True, strategy=strategy),
        "bid": _check(
            bid is not None and bid > 0,
            bid=bid,
            threshold=0,
        ),
        "ask": _check(
            ask is not None and ask > 0,
            ask=ask,
            threshold=0,
        ),
        "volume": _check(
            volume is not None and volume >= MIN_VOLUME,
            volume=volume,
            threshold=MIN_VOLUME,
        ),
        "spread": _check(
            spread_pct is not None and spread_pct <= MAX_SPREAD_PCT,
            spreadAbs=spread_abs,
            spreadPct=spread_pct,
            thresholdPct=MAX_SPREAD_PCT,
        ),
        "priceDeviation": _check(
            deviation_pct is not None and deviation_pct <= PRICE_DEVIATION_THRESHOLD_PCT,
            alertPrice=alert_price,
            currentPrice=current_price,
            deviationPct=deviation_pct,
            thresholdPct=PRICE_DEVIATION_THRESHOLD_PCT,
        ),
        "liquidity": _check(
            bid is not None and bid > 0
            and ask is not None and ask > 0
            and volume is not None and volume >= MIN_VOLUME,
            bid=bid,
            ask=ask,
            volume=volume,
            openInterest=option_liquidity.get("openInterest"),
        ),
        "riskReward": _check(
            risk_reward is not None and risk_reward >= MIN_RISK_REWARD,
            entry=entry,
            stop=stop,
            target=target,
            riskReward=risk_reward,
            estimatedLossPerContract=move_estimates.get("estimatedLossPerContract"),
            estimatedRewardPerContract=move_estimates.get("estimatedRewardPerContract"),
            threshold=MIN_RISK_REWARD,
        ),
    }

    failed = [
        name for name, check in checks.items()
        if check.get("validation") is not True
    ]
    decision = "VALID" if not failed else "REJECT"
    reason = (
        "Alert validation passed"
        if decision == "VALID"
        else "Alert validation failed: " + ", ".join(failed)
    )

    return {
        "status": "ok",
        "decision": decision,
        "reason": reason,
        "checks": checks,
    }
