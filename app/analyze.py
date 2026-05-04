def analyze_normalized(normalized: dict):
    premium = normalized["trade"].get("premium") or 0

    if premium >= 10000:
        decision = "VALID"
        reason = "Premium igual o superior a 10000"
    else:
        decision = "REJECT"
        reason = "Premium inferior a 10000"

    return {
        "decision": decision,
        "reason": reason,
        "order": {
            "entry": None,
            "stopLoss": None,
            "takeProfit": None
        },
        "checks": {
            "premium_ok": premium >= 10000
        }
    }
