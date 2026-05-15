import os
from typing import Optional


DEBUG_OPTION_CHAIN = os.getenv("DEBUG_OPTION_CHAIN", "").lower() in ("1", "true", "yes")


def _should_debug_pseudo_gex(normalized: dict) -> bool:
    option = normalized.get("option") or {}
    return DEBUG_OPTION_CHAIN or option.get("underlying") == "MSFT"


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


def _calculate_pseudo_gex_score(row: dict, price: float) -> Optional[dict]:
    strike = _safe_float(row.get("strike"))
    option_type = row.get("type")

    if strike is None or option_type is None:
        return None

    open_interest = _safe_float(row.get("openInterest")) or 0
    volume = _safe_float(row.get("volume")) or 0

    if open_interest <= 0 and volume <= 0:
        return None

    base_score = (open_interest * 0.4) + (volume * 0.6)
    distance_pct = abs(strike - price) / price * 100
    final_score = base_score / (1 + distance_pct * 2)

    return {
        "strike": strike,
        "type": option_type,
        "openInterest": open_interest,
        "volume": volume,
        "distance_pct": distance_pct,
        "base_score": base_score,
        "final_score": final_score
    }


def calculate_support_resistance(normalized: dict, market_context: dict) -> dict:
    underlying = market_context.get("underlying") or {}
    price = _safe_float(underlying.get("price"))

    if price is None:
        return {
            "pseudo_gex_support": None,
            "pseudo_gex_resistance": None
        }

    support = None
    resistance = None
    support_score = None
    resistance_score = None
    debug_candidates = []

    for row in market_context.get("optionChain") or []:
        score = _calculate_pseudo_gex_score(row, price)

        if score is None:
            continue

        strike = score["strike"]
        option_type = score["type"]
        final_score = score["final_score"]

        if _should_debug_pseudo_gex(normalized):
            debug_candidates.append(score)

        if option_type == "PUT" and strike < price:
            if support_score is None or final_score > support_score:
                support = strike
                support_score = final_score

        if option_type == "CALL" and strike > price:
            if resistance_score is None or final_score > resistance_score:
                resistance = strike
                resistance_score = final_score

    result = {
        "pseudo_gex_support": support,
        "pseudo_gex_resistance": resistance
    }

    if _should_debug_pseudo_gex(normalized):
        option = normalized.get("option") or {}
        print("[PSEUDO_GEX_DEBUG]", option.get("underlying"), {
            "candidates": debug_candidates,
            "selected": result
        })

    return result


def calculate_indicators(normalized: dict, market_context: dict) -> dict:
    support_resistance = calculate_support_resistance(normalized, market_context)

    return {
        "price_deviation_pct": _calculate_price_deviation_pct(normalized, market_context),
        "spread_pct": _calculate_spread_pct(market_context),
        **support_resistance
    }


def calculate_historical_volatility(*args, **kwargs) -> Optional[float]:
    return None


def calculate_iv_hv_ratio(*args, **kwargs) -> Optional[float]:
    return None
