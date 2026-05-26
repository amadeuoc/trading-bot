import math
import os
from typing import Any, Dict, List, Optional

from app.market_data.gex import build_gex_context
from app.market_data.ibkr import ibkr_session

IB_EXCHANGE = "SMART"
IB_CURRENCY = "USD"
IB_QUOTE_WAIT_SECONDS = 1.5
DEBUG_OPTION_CHAIN = os.getenv("DEBUG_OPTION_CHAIN", "").lower() in ("1", "true", "yes")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


GEX_ULTRA_SHORT_RANGE_PCT = _env_float("GEX_ULTRA_SHORT_RANGE_PCT", 0.05)


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
            "symbol": None,
            "underlying": None,
            "type": None,
            "strike": None,
            "expiration": None,
            "dte": None,
            "ask": None,
            "bid": None,
            "last": None,
            "volume": None,
            "open_interest": None,
            "gamma": None
        },
        "underlying": {
            "symbol": None,
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


def _get_option_dte(normalized: dict) -> Optional[int]:
    option = normalized.get("option") or {}
    expiration = option.get("expiration")
    if not expiration:
        return None

    try:
        from datetime import date, datetime

        expiration_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        return max((expiration_date - date.today()).days, 0)
    except (TypeError, ValueError):
        return None


def _get_option_metadata(normalized: dict) -> Dict[str, Any]:
    option = normalized.get("option") or {}
    return {
        "symbol": option.get("symbol"),
        "underlying": option.get("underlying"),
        "type": option.get("type"),
        "strike": _safe_float(option.get("strike")),
        "expiration": option.get("expiration"),
        "dte": _get_option_dte(normalized)
    }


def _get_option_gamma(ticker) -> Optional[float]:
    for attr in ("modelGreeks", "lastGreeks", "bidGreeks", "askGreeks"):
        greeks = getattr(ticker, attr, None)
        gamma = _safe_float(getattr(greeks, "gamma", None)) if greeks else None
        if gamma is not None:
            return gamma
    return None


def _wait_for_option_gamma(
    ib,
    ticker,
    max_wait_seconds=3.0,
    step_seconds=0.25
) -> Optional[float]:
    elapsed = 0
    while elapsed < max_wait_seconds:
        gamma = _get_option_gamma(ticker)
        if gamma is not None:
            return gamma
        ib.sleep(step_seconds)
        elapsed += step_seconds
    return _get_option_gamma(ticker)


def _wait_for_option_gammas(
    ib,
    tickers,
    max_wait_seconds=3.0,
    step_seconds=0.25
) -> None:
    pending = set(range(len(tickers)))
    elapsed = 0

    while pending and elapsed < max_wait_seconds:
        resolved = {
            index for index in pending
            if _get_option_gamma(tickers[index]) is not None
        }
        pending -= resolved
        if not pending:
            return

        ib.sleep(step_seconds)
        elapsed += step_seconds


def _get_option_last(ticker) -> Optional[float]:
    last = _safe_float(getattr(ticker, "last", None))
    if last is not None and last > 0:
        return last

    market_price = _safe_float(ticker.marketPrice())
    if market_price is not None and market_price > 0:
        return market_price

    return None


def _has_option_market_data(ticker, open_interest=None) -> bool:
    return any(
        value is not None
        for value in (
            _safe_float(getattr(ticker, "bid", None)),
            _safe_float(getattr(ticker, "ask", None)),
            _get_option_last(ticker),
            _safe_float(getattr(ticker, "volume", None)),
            _safe_float(open_interest),
        )
    )


def _debug_missing_gamma(
    underlying,
    expiration,
    option_type,
    strike,
    ticker,
    open_interest=None
) -> None:
    if not _should_debug_option_chain(underlying):
        return
    if not _has_option_market_data(ticker, open_interest=open_interest):
        return

    print(
        "[OPTION_CHAIN] missing gamma for",
        underlying,
        expiration,
        option_type,
        strike,
        "with bid/ask/volume/OI available"
    )


def _debug_unknown_option_contract(underlying, expiration, right, strike) -> None:
    print(
        "[IBKR] Skipping unknown option contract:",
        underlying,
        expiration,
        right,
        strike
    )


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
    qualified_contracts = ib.qualifyContracts(contract)
    if not qualified_contracts:
        _debug_unknown_option_contract(
            underlying,
            expiration,
            right,
            option.get("strike")
        )
        return {
            "ask": None,
            "bid": None,
            "last": None,
            "volume": None,
            "open_interest": None,
            "gamma": None
        }
    contract = qualified_contracts[0]

    # Generic ticks 100/101 may expose option volume/open interest depending on
    # IBKR subscriptions and exchange support. Open interest is not guaranteed.
    ticker = None
    try:
        ticker = ib.reqMktData(contract, "100,101", False, False, [])
        ib.sleep(IB_QUOTE_WAIT_SECONDS)

        open_interest = (
            _safe_float(getattr(ticker, "callOpenInterest", None))
            if option.get("type") == "CALL"
            else _safe_float(getattr(ticker, "putOpenInterest", None))
        )
        gamma = _wait_for_option_gamma(ib, ticker)

        quote = {
            "ask": _safe_float(ticker.ask),
            "bid": _safe_float(ticker.bid),
            "last": _get_option_last(ticker),
            "volume": _safe_float(ticker.volume),
            "open_interest": open_interest,
            "gamma": gamma
        }
        if quote["gamma"] is None:
            _debug_missing_gamma(
                underlying,
                option.get("expiration") or expiration,
                option.get("type"),
                option.get("strike"),
                ticker,
                open_interest=open_interest
            )

        return quote
    finally:
        if ticker is not None:
            ib.cancelMktData(contract)


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
    display_expiration = option.get("expiration") or expiration
    dte = _get_option_dte(normalized)
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

    lower_bound = current_price * (1 - GEX_ULTRA_SHORT_RANGE_PCT)
    upper_bound = current_price * (1 + GEX_ULTRA_SHORT_RANGE_PCT)
    strikes_in_range = [
        strike for strike in strikes
        if lower_bound <= strike <= upper_bound
    ]

    _debug_option_chain(underlying, "after strike filter", {
        "rangePct": GEX_ULTRA_SHORT_RANGE_PCT,
        "strikeCount": len(strikes_in_range),
        "strikes": sorted(strikes_in_range)[:40]
    })

    alert_type = option.get("type")
    alert_strike = _safe_float(target_strike)
    selected_strikes = set(strikes_in_range)

    if alert_strike is not None:
        selected_strikes.add(alert_strike)

    _debug_option_chain(underlying, "gex strike set", {
        "alertType": alert_type,
        "alertStrike": alert_strike,
        "strikeCount": len(selected_strikes),
        "strikes": sorted(selected_strikes)[:40]
    })

    # GEX is calculated per strike, so every selected strike needs both the
    # CALL and PUT side. The alerted contract is included even when it is
    # outside the default range.
    rows = []
    seen_contracts = set()
    subscriptions = []

    try:
        for option_type, right in (
            ("CALL", "C"),
            ("PUT", "P"),
        ):
            for strike in sorted(selected_strikes):
                contract_key = (option_type, _safe_float(strike))
                if contract_key in seen_contracts:
                    continue
                seen_contracts.add(contract_key)

                contract = Option(
                    underlying,
                    expiration,
                    strike,
                    right,
                    IB_EXCHANGE,
                    currency=IB_CURRENCY
                )
                qualified_contracts = ib.qualifyContracts(contract)
                if not qualified_contracts:
                    _debug_unknown_option_contract(
                        underlying,
                        expiration,
                        right,
                        strike
                    )
                    continue
                contract = qualified_contracts[0]

                ticker = ib.reqMktData(contract, "100,101", False, False, [])
                subscriptions.append({
                    "contract": contract,
                    "ticker": ticker,
                    "strike": strike,
                    "option_type": option_type
                })

        if subscriptions:
            ib.sleep(IB_QUOTE_WAIT_SECONDS)
            _wait_for_option_gammas(
                ib,
                [item["ticker"] for item in subscriptions]
            )

        for item in subscriptions:
            ticker = item["ticker"]
            strike = item["strike"]
            option_type = item["option_type"]

            open_interest = (
                _safe_float(getattr(ticker, "callOpenInterest", None))
                if option_type == "CALL"
                else _safe_float(getattr(ticker, "putOpenInterest", None))
            )
            gamma = _get_option_gamma(ticker)
            if gamma is None:
                _debug_missing_gamma(
                    underlying,
                    display_expiration,
                    option_type,
                    strike,
                    ticker,
                    open_interest=open_interest
                )

            rows.append({
                "expiry": display_expiration,
                "dte": dte,
                "strike": _safe_float(strike),
                "option_type": option_type,
                "gamma": gamma,
                "open_interest": open_interest,
                "volume": _safe_float(ticker.volume),
                "bid": _safe_float(ticker.bid),
                "ask": _safe_float(ticker.ask),
                "last": _get_option_last(ticker),
                "is_alert_contract": (
                    option_type == alert_type
                    and alert_strike is not None
                    and _safe_float(strike) == alert_strike
                )
            })
    finally:
        for item in subscriptions:
            ib.cancelMktData(item["contract"])

    _debug_option_chain(underlying, "final optionChain", {
        "length": len(rows)
    })

    return rows


def _attach_gex_context(
    context: Dict[str, Any],
    current_price: Optional[float],
    underlying: Optional[str]
) -> None:
    option_chain = context.get("optionChain") or []
    rows_with_gamma = [
        row for row in option_chain
        if _safe_float(row.get("gamma")) is not None
    ]

    debug_data = {
        "optionChainRows": len(option_chain),
        "rowsWithGamma": len(rows_with_gamma),
        "rowsWithOI": len([row for row in option_chain if row.get("open_interest") is not None]),
        "rowsWithVolume": len([row for row in option_chain if row.get("volume") is not None]),
        "gexBuilt": False
    }

    if current_price is None or current_price <= 0 or not option_chain or not rows_with_gamma:
        context["gex_context"] = None
        _debug_option_chain(underlying, "gex context", debug_data)
        return

    gex_context = build_gex_context(
        option_chain,
        current_price,
        dte_max=7,
        range_pct=GEX_ULTRA_SHORT_RANGE_PCT,
        source="ibkr"
    )
    context["gex_context"] = gex_context.model_dump()
    debug_data["gexBuilt"] = True
    _debug_option_chain(underlying, "gex context", debug_data)


def _enrich_option_from_alert_contract(context: Dict[str, Any]) -> None:
    option = context.get("option") or {}
    option_chain = context.get("optionChain") or []
    alert_contract = next(
        (
            row for row in option_chain
            if isinstance(row, dict) and row.get("is_alert_contract") is True
        ),
        None
    )

    if not alert_contract:
        return

    for field in ("open_interest", "volume", "bid", "ask", "last", "gamma"):
        if option.get(field) is None:
            option[field] = alert_contract.get(field)

    context["option"] = option


def get_ultra_short_market_context(normalized: dict) -> Dict[str, Any]:
    context = _empty_market_context()

    try:
        with ibkr_session() as ib:
            underlying = _get_option_underlying(normalized)
            if not underlying:
                return context

            current_price = _get_underlying_price(ib, underlying)
            context["underlying"]["symbol"] = underlying
            context["underlying"]["price"] = current_price
            context["option"] = _get_option_metadata(normalized)
            context["optionChain"] = _get_option_chain_oi_proxy(
                ib,
                normalized,
                current_price
            )
            _enrich_option_from_alert_contract(context)
            if (
                context["option"].get("bid") is None
                or context["option"].get("ask") is None
            ):
                context["option"].update(_get_option_quote(ib, normalized))
            _attach_gex_context(context, current_price, underlying)

    except Exception as exc:
        print("[MARKET_DATA_ERROR]", exc)

    return context
