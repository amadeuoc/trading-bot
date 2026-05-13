import re
from datetime import datetime


def parse_option_symbol(symbol: str):
    if not symbol or not symbol.startswith("O:"):
        return None

    raw = symbol.split(":")[1]

    match = re.match(r"([A-Z]+)(\d{6})([CP])(\d+)", raw)
    if not match:
        return None

    ticker, date, cp, strike_raw = match.groups()

    year = int("20" + date[:2])
    month = int(date[2:4])
    day = int(date[4:6])

    strike = int(strike_raw) / 1000

    return {
        "underlying": ticker,
        "type": "CALL" if cp == "C" else "PUT",
        "strike": strike,
        "expiration": datetime(year, month, day).strftime("%Y-%m-%d")
    }


def normalize_alert(alert: dict):
    symbol = alert.get("symbol")
    option = parse_option_symbol(symbol)

    if option is None:
        return None

    return {
        "underlying": option["underlying"],

        "option": {
            "underlying": option["underlying"],
            "symbol": symbol,
            "type": option["type"],
            "strike": option["strike"],
            "expiration": option["expiration"]
        },

        "trade": {
            "price": alert.get("tradePrice"),
            "premium": alert.get("alertPremium"),
            "spread_execution": alert.get("spread_execution")
        },

        "alert": {
            "id": alert.get("id"),
            "type": alert.get("alertType"),
            "filterName": alert.get("filterName"),
            "user": alert.get("user"),
            "timestamp": alert.get("timestamp")
        }
    }
