from datetime import date, datetime
import time


ticker_flows = {}


def get_dte(expiry):
    if not expiry:
        return None

    try:
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None

    return max((expiry_date - date.today()).days, 0)


def classify_strategy(dte):
    if dte is None:
        return "unknown"
    if dte <= 5:
        return "ultra_short"
    if dte <= 21:
        return "short"
    if dte <= 90:
        return "swing"
    return "long"


def get_sentiment(normalized):
    option = normalized.get("option") or {}
    meta = normalized.get("meta") or {}

    contract_type = (option.get("type") or "").upper()
    spread_execution = (meta.get("spread_execution") or "").upper()

    if not spread_execution or spread_execution == "MID":
        return "neutral"

    if contract_type == "CALL" and spread_execution == "ASK":
        return "bullish"
    if contract_type == "CALL" and spread_execution == "BID":
        return "bearish"
    if contract_type == "PUT" and spread_execution == "ASK":
        return "bearish"
    if contract_type == "PUT" and spread_execution == "BID":
        return "bullish"

    return "neutral"


def get_ticker(normalized):
    meta = normalized.get("meta") or {}
    return meta.get("ticker")


def get_alert_timestamp(normalized):
    meta = normalized.get("meta") or {}
    timestamp = meta.get("timestamp")

    if timestamp is None:
        return int(time.time())

    try:
        timestamp = int(timestamp)
    except (TypeError, ValueError):
        return int(time.time())

    if timestamp > 1000000000000:
        return timestamp // 1000

    return timestamp


def clean_old_flows():
    cutoff = int(time.time()) - 86400

    for ticker in list(ticker_flows.keys()):
        ticker_flows[ticker] = [
            alert
            for alert in ticker_flows[ticker]
            if alert.get("time", 0) >= cutoff
        ]

        if not ticker_flows[ticker]:
            del ticker_flows[ticker]


def add_to_flow(normalized, classification):
    ticker = get_ticker(normalized)
    if not ticker:
        return

    option = normalized.get("option") or {}
    meta = normalized.get("meta") or {}

    ticker_flows.setdefault(ticker, []).append({
        "time": get_alert_timestamp(normalized),
        "sentiment": classification["sentiment"],
        "dte": classification["dte"],
        "strategy": classification["strategy"],
        "contractType": option.get("type"),
        "spread_execution": meta.get("spread_execution"),
        "filterName": meta.get("filterName"),
        "source": meta.get("source")
    })

    print(
        "[FLOW]",
        ticker,
        option.get("symbol"),
        classification["sentiment"],
        meta.get("spread_execution"),
        len(ticker_flows[ticker])
    )


def get_ticker_alerts_today(ticker):
    if not ticker:
        return []
    return list(ticker_flows.get(ticker, []))


def classify_alert(normalized):
    option = normalized.get("option") or {}

    dte = get_dte(option.get("expiration"))
    classification = {
        "sentiment": get_sentiment(normalized),
        "strategy": classify_strategy(dte),
        "dte": dte,
        "tickerAlertsToday": []
    }

    clean_old_flows()
    add_to_flow(normalized, classification)
    classification["tickerAlertsToday"] = get_ticker_alerts_today(get_ticker(normalized))

    return classification
