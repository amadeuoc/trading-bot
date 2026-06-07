from datetime import datetime
from typing import Optional


def build_polygon_option_symbol(ticker, expiration, right, strike) -> Optional[str]:
    if not ticker or not expiration or not right:
        return None

    option_right = str(right).upper()
    if option_right not in ("CALL", "PUT", "C", "P"):
        return None

    try:
        expiration_date = datetime.strptime(str(expiration), "%Y-%m-%d")
        strike_value = float(strike)
    except (TypeError, ValueError):
        return None

    if strike_value <= 0:
        return None

    right_code = "C" if option_right in ("CALL", "C") else "P"
    date_code = expiration_date.strftime("%y%m%d")
    strike_code = f"{int(round(strike_value * 1000)):08d}"
    return f"O:{str(ticker).upper()}{date_code}{right_code}{strike_code}"
