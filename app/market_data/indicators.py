from typing import Optional


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


def _calculate_spread_abs(market_context: dict) -> Optional[float]:
    option = market_context.get("option") or {}

    bid = _safe_positive_float(option.get("bid"))
    ask = _safe_positive_float(option.get("ask"))

    if bid is None or ask is None:
        return None

    return ask - bid


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
    support_oi = None
    resistance_oi = None

    for row in market_context.get("optionChain") or []:
        strike = _safe_float(row.get("strike"))
        open_interest = _safe_float(row.get("openInterest"))
        option_type = row.get("type")

        if strike is None or open_interest is None or open_interest <= 0:
            continue

        if option_type == "PUT" and strike < price:
            if support_oi is None or open_interest > support_oi:
                support = strike
                support_oi = open_interest

        if option_type == "CALL" and strike > price:
            if resistance_oi is None or open_interest > resistance_oi:
                resistance = strike
                resistance_oi = open_interest

    return {
        "pseudo_gex_support": support,
        "pseudo_gex_resistance": resistance
    }


def calculate_indicators(normalized: dict, market_context: dict) -> dict:
    support_resistance = calculate_support_resistance(normalized, market_context)

    return {
        "price_deviation_pct": _calculate_price_deviation_pct(normalized, market_context),
        "spread_abs": _calculate_spread_abs(market_context),
        "spread_pct": _calculate_spread_pct(market_context),
        **support_resistance
    }


def calculate_historical_volatility(*args, **kwargs) -> Optional[float]:
    return None


def calculate_iv_hv_ratio(*args, **kwargs) -> Optional[float]:
    return None
