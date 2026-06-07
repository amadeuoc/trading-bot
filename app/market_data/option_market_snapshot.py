import math
from typing import Optional

from app.market_data.ibkr import ibkr_session
from app.utils.options import build_polygon_option_symbol


IB_EXCHANGE = "SMART"
IB_CURRENCY = "USD"
IB_QUOTE_WAIT_SECONDS = 1.5


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _ib_option_expiration(expiration: Optional[str]) -> Optional[str]:
    if not expiration:
        return None
    return expiration.replace("-", "")


def _empty_option_greeks():
    return {
        "delta": None,
        "gamma": None,
        "theta": None,
        "vega": None,
        "rho": None,
        "iv": None,
        "implied_volatility": None,
    }


def _get_option_greeks(ticker):
    for attr in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks"):
        greeks = getattr(ticker, attr, None)
        if not greeks:
            continue

        implied_volatility = _safe_float(getattr(greeks, "impliedVol", None))
        values = {
            "delta": _safe_float(getattr(greeks, "delta", None)),
            "gamma": _safe_float(getattr(greeks, "gamma", None)),
            "theta": _safe_float(getattr(greeks, "theta", None)),
            "vega": _safe_float(getattr(greeks, "vega", None)),
            "rho": _safe_float(getattr(greeks, "rho", None)),
            "iv": implied_volatility,
            "implied_volatility": implied_volatility,
        }
        if any(value is not None for value in values.values()):
            return values

    return _empty_option_greeks()


def _get_option_gamma(ticker) -> Optional[float]:
    return _get_option_greeks(ticker).get("gamma")


def _wait_for_option_gamma(ib, ticker, max_wait_seconds=3.0, step_seconds=0.25):
    elapsed = 0
    while elapsed < max_wait_seconds:
        gamma = _get_option_gamma(ticker)
        if gamma is not None:
            return gamma
        ib.sleep(step_seconds)
        elapsed += step_seconds
    return _get_option_gamma(ticker)


def _get_option_last(ticker) -> Optional[float]:
    last = _safe_float(getattr(ticker, "last", None))
    if last is not None and last > 0:
        return last

    market_price = _safe_float(ticker.marketPrice())
    if market_price is not None and market_price > 0:
        return market_price

    return None


def _get_underlying_price(ib, ticker_symbol: str) -> Optional[float]:
    from ib_insync import Stock

    contract = Stock(ticker_symbol, IB_EXCHANGE, IB_CURRENCY)
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        return None

    contract = qualified[0]
    ticker = None
    try:
        ticker = ib.reqMktData(contract, "", False, False, [])
        ib.sleep(IB_QUOTE_WAIT_SECONDS)

        return (
            _safe_float(ticker.marketPrice())
            or _safe_float(ticker.last)
            or _safe_float(ticker.close)
            or _safe_float(ticker.bid)
            or _safe_float(ticker.ask)
        )
    finally:
        if ticker is not None:
            ib.cancelMktData(contract)


def _get_option_quote(ib, ticker, right, expiration, strike):
    from ib_insync import Option

    expiration_code = _ib_option_expiration(expiration)
    right_code = "C" if right == "CALL" else "P"
    contract = Option(
        ticker,
        expiration_code,
        strike,
        right_code,
        IB_EXCHANGE,
        currency=IB_CURRENCY,
    )
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        return None

    contract = qualified[0]
    market_ticker = None
    try:
        market_ticker = ib.reqMktData(contract, "100,101", False, False, [])
        ib.sleep(IB_QUOTE_WAIT_SECONDS)
        gamma = _wait_for_option_gamma(ib, market_ticker)
        greeks = _get_option_greeks(market_ticker)

        open_interest = (
            _safe_float(getattr(market_ticker, "callOpenInterest", None))
            if right == "CALL"
            else _safe_float(getattr(market_ticker, "putOpenInterest", None))
        )

        return {
            "bid": _safe_float(market_ticker.bid),
            "ask": _safe_float(market_ticker.ask),
            "last": _get_option_last(market_ticker),
            "volume": _safe_float(market_ticker.volume),
            "open_interest": open_interest,
            **greeks,
            "gamma": gamma if gamma is not None else greeks.get("gamma"),
        }
    finally:
        if market_ticker is not None:
            ib.cancelMktData(contract)


def get_option_market_snapshot(ticker, right, expiration, strike):
    option_right = str(right or "").upper()
    if option_right not in ("CALL", "PUT"):
        return None

    option_symbol = build_polygon_option_symbol(
        ticker,
        expiration,
        option_right,
        strike,
    )
    if option_symbol is None:
        return None

    with ibkr_session() as ib:
        underlying_price = _get_underlying_price(ib, ticker)
        option_quote = _get_option_quote(
            ib,
            str(ticker).upper(),
            option_right,
            expiration,
            strike,
        )

    if option_quote is None:
        return None

    return {
        "underlying": {
            "symbol": str(ticker).upper(),
            "price": underlying_price,
        },
        "option": {
            "symbol": option_symbol,
            "underlying": str(ticker).upper(),
            "type": option_right,
            "strike": _safe_float(strike),
            "expiration": expiration,
            **option_quote,
        },
    }
