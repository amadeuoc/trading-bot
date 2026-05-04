from app.classify import classify_alert


def analyze_normalized(normalized: dict):
    premium = normalized["trade"].get("premium") or 0
    classification = classify_alert(normalized)

    if premium >= 10000:
        decision = "VALID"
        reason = "Premium igual o superior a 10000"
    else:
        decision = "REJECT"
        reason = "Premium inferior a 10000"

    return {
        "decision": decision,
        "reason": reason,
        "classification": classification,
        "order": {
            "entry": None,
            "stopLoss": None,
            "takeProfit": None
        },
        "checks": {
            "premium_ok": premium >= 10000
        }
    }
