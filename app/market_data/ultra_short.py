import math
import os
from typing import Any, Dict, List, Optional

from app.market_data.ibkr import ibkr_session

IB_EXCHANGE = "SMART"
IB_CURRENCY = "USD"
IB_QUOTE_WAIT_SECONDS = 1.5
DEBUG_OPTION_CHAIN = os.getenv("DEBUG_OPTION_CHAIN", "").lower() in ("1", "true", "yes")


def _should_debug_option_chain(underlying: Optional[str]) -> bool:
    return DEBUG_OPTION_CHAIN or underlying == "MSFT"


def _debug_option_chain(underlying: Optional[str], message: str, data=None) -> None:
    if not _should_debug_option_chain(underlying):
        return
    if data is None:
        print("[OPTION_CHAIN_DEBUG]", underlying, message)
    else:
        print("[OPTION_CHAIN_DEBUG]", underlying, message, data)


def _empty_market_context() -> Dict[str, Any]:
    return {
        "option": {
            "ask": None,
            "bid": None,
            "volume": None,
            "openInterest": None
        },
        "underlying": {
            "price": None
        },
        "optionChain": []
    }


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


def _get_option_underlying(normalized: dict) -> Optional[str]:
    option = normalized.get("option") or {}
    return option.get("underlying")


def _get_underlying_price(ib, ticker_symbol: str) -> Optional[float]:
    from ib_insync import Stock

    contract = Stock(ticker_symbol, IB_EXCHANGE, IB_CURRENCY)
    ib.qualifyContracts(contract)

    ticker = ib.reqMktData(contract, "", False, False, [])
    ib.sleep(IB_QUOTE_WAIT_SECONDS)

    price = (
        _safe_float(ticker.marketPrice())
        or _safe_float(ticker.last)
        or _safe_float(ticker.close)
        or _safe_float(ticker.bid)
        or _safe_float(ticker.ask)
    )

    ib.cancelMktData(contract)
    return price


def _get_option_quote(ib, normalized: dict) -> Dict[str, Optional[float]]:
    from ib_insync import Option

    option = normalized.get("option") or {}
    underlying = option.get("underlying")
    expiration = _ib_option_expiration(option.get("expiration"))
    right = "C" if option.get("type") == "CALL" else "P"

    contract = Option(
        underlying,
        expiration,
        option.get("strike"),
        right,
        IB_EXCHANGE,
        currency=IB_CURRENCY
    )
    ib.qualifyContracts(contract)

    # Generic ticks 100/101 may expose option volume/open interest depending on
    # IBKR subscriptions and exchange support. Open interest is not guaranteed.
    ticker = ib.reqMktData(contract, "100,101", False, False, [])
    ib.sleep(IB_QUOTE_WAIT_SECONDS)

    open_interest = (
        _safe_float(getattr(ticker, "callOpenInterest", None))
        if option.get("type") == "CALL"
        else _safe_float(getattr(ticker, "putOpenInterest", None))
    )

    quote = {
        "ask": _safe_float(ticker.ask),
        "bid": _safe_float(ticker.bid),
        "volume": _safe_float(ticker.volume),
        "openInterest": open_interest
    }

    ib.cancelMktData(contract)
    return quote


def _get_option_chain_oi_proxy(
    ib,
    normalized: dict,
    current_price: Optional[float]
) -> List[Dict[str, Optional[float]]]:
    from ib_insync import Option, Stock

    if current_price is None:
        return []

    option = normalized.get("option") or {}
    underlying = option.get("underlying")
    expiration = _ib_option_expiration(option.get("expiration"))
    target_strike = option.get("strike")

    _debug_option_chain(underlying, "request", {
        "optionSymbol": option.get("symbol"),
        "targetExpiration": expiration,
        "targetStrike": target_strike,
        "underlyingPrice": current_price
    })

    stock = Stock(underlying, IB_EXCHANGE, IB_CURRENCY)
    qualified = ib.qualifyContracts(stock)
    if not qualified:
        return []

    chains = ib.reqSecDefOptParams(
        underlying,
        "",
        stock.secType,
        stock.conId
    )

    _debug_option_chain(underlying, "raw chains", {
        "count": len(chains),
        "first3": [
            {
                "exchange": item.exchange,
                "tradingClass": item.tradingClass,
                "expirations": sorted(item.expirations)[:5],
                "strikeCount": len(item.strikes)
            }
            for item in chains[:3]
        ],
        "availableExpirations": sorted({
            exp
            for item in chains
            for exp in item.expirations
        })[:20]
    })

    matching_chains = [
        item for item in chains
        if expiration in item.expirations
    ]
    if not matching_chains:
        _debug_option_chain(underlying, "no chains after expiration filter", {
            "targetExpiration": expiration
        })
        return []

    smart_chains = [item for item in matching_chains if item.exchange == IB_EXCHANGE]
    selected_chains = smart_chains or matching_chains
    strikes = sorted({
        strike
        for item in selected_chains
        for strike in item.strikes
    })

    _debug_option_chain(underlying, "after expiration filter", {
        "matchingChains": len(matching_chains),
        "selectedChains": len(selected_chains),
        "selectedExchanges": sorted({item.exchange for item in selected_chains}),
        "rawStrikeCount": len(strikes)
    })

    call_strikes = [
        strike for strike in strikes
        if current_price < strike <= current_price * 1.05
    ]
    put_strikes = [
        strike for strike in strikes
        if current_price * 0.95 <= strike < current_price
    ]

    _debug_option_chain(underlying, "after strike filter", {
        "callStrikeCount": len(call_strikes),
        "putStrikeCount": len(put_strikes),
        "callStrikes": sorted(call_strikes)[:20],
        "putStrikes": sorted(put_strikes)[:20]
    })

    # For ultra-short flow we need nearby option pressure on both sides:
    # calls above spot for resistance context and puts below spot for support
    # context. Filtering to +/- 5% keeps IBKR snapshot requests small.
    rows = []
    for option_type, right, strikes in (
        ("CALL", "C", sorted(call_strikes)),
        ("PUT", "P", sorted(put_strikes)),
    ):
        for strike in strikes:
            contract = Option(
                underlying,
                expiration,
                strike,
                right,
                IB_EXCHANGE,
                currency=IB_CURRENCY
            )
            ib.qualifyContracts(contract)

            # Open interest is best-effort from market data ticks. IBKR often
            # returns None unless the subscription and venue support it.
            ticker = ib.reqMktData(contract, "100,101", False, False, [])
            ib.sleep(IB_QUOTE_WAIT_SECONDS)

            open_interest = (
                _safe_float(getattr(ticker, "callOpenInterest", None))
                if option_type == "CALL"
                else _safe_float(getattr(ticker, "putOpenInterest", None))
            )

            rows.append({
                "strike": _safe_float(strike),
                "type": option_type,
                "openInterest": open_interest,
                "volume": _safe_float(ticker.volume),
                "bid": _safe_float(ticker.bid),
                "ask": _safe_float(ticker.ask)
            })

            ib.cancelMktData(contract)

    _debug_option_chain(underlying, "final optionChain", {
        "length": len(rows)
    })

    return rows


def get_ultra_short_market_context(normalized: dict) -> Dict[str, Any]:
    context = _empty_market_context()

    try:
        with ibkr_session() as ib:
            underlying = _get_option_underlying(normalized)
            if not underlying:
                return context

            current_price = _get_underlying_price(ib, underlying)
            context["underlying"]["price"] = current_price
            context["option"] = _get_option_quote(ib, normalized)
            context["optionChain"] = _get_option_chain_oi_proxy(
                ib,
                normalized,
                current_price
            )

    except Exception as exc:
        print("[MARKET_DATA_ERROR]", exc)

    return context
