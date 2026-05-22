import os
from typing import Optional


DEBUG_OPTION_CHAIN = os.getenv("DEBUG_OPTION_CHAIN", "").lower() in ("1", "true", "yes")


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


def _get_liquidity(market_context: dict) -> dict:
    option = market_context.get("option") or {}
    return {
        "bid": _safe_float(option.get("bid")),
        "ask": _safe_float(option.get("ask")),
        "volume": _safe_float(option.get("volume")),
        "open_interest": _safe_float(option.get("open_interest"))
    }


def calculate_indicators(normalized: dict, market_context: dict) -> dict:
    indicators = {
        "price_deviation_pct": _calculate_price_deviation_pct(normalized, market_context),
        "spread": _calculate_spread(market_context),
        "spread_pct": _calculate_spread_pct(market_context),
        "liquidity": _get_liquidity(market_context)
    }

    if market_context.get("gex_context"):
        indicators["gex"] = market_context["gex_context"]

    return indicators


def calculate_historical_volatility(*args, **kwargs) -> Optional[float]:
    return None


def calculate_iv_hv_ratio(*args, **kwargs) -> Optional[float]:
    return None
