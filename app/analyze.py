from app.classify import classify_alert
from app.market_data.indicators import calculate_indicators
from app.market_data.provider import get_market_context
from app.validators.router import validate_by_strategy


def _get_ticker_context(classification):
    if isinstance(classification, dict):
        return classification.get("tickerAlertsToday")
    return getattr(classification, "tickerAlertsToday", None)


def _serialize_market_context(market_context):
    if market_context is None:
        return None
    if hasattr(market_context, "model_dump"):
        return market_context.model_dump()
    return market_context


def _attach_indicators(normalized: dict, market_context):
    if not isinstance(market_context, dict):
        return

    try:
        market_context["indicators"] = calculate_indicators(normalized, market_context)
    except Exception as exc:
        market_context["indicators"] = {}
        market_context["indicatorError"] = str(exc)


def analyze_normalized(normalized: dict):
    premium = normalized["trade"].get("premium") or 0
    classification = classify_alert(normalized)
    market_context = get_market_context(normalized, classification)
    _attach_indicators(normalized, market_context)
    strategy_validation = validate_by_strategy(
        normalized,
        classification,
        market_context=market_context,
        ticker_context=_get_ticker_context(classification)
    )

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
        "marketContext": _serialize_market_context(market_context),
        "strategyValidation": strategy_validation,
        "order": {
            "entry": None,
            "stopLoss": None,
            "takeProfit": None
        },
        "checks": {
            "premium_ok": premium >= 10000
        }
    }
