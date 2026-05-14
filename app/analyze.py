from datetime import datetime
from zoneinfo import ZoneInfo

from app.classify import classify_alert
from app.market_data.indicators import calculate_indicators
from app.market_data.provider import get_market_context
from app.validators.router import validate_by_strategy


MARKET_TZ = ZoneInfo("America/New_York")


def _timestamp_to_market_datetime(timestamp):
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return None

    # Support milliseconds if needed.
    if ts > 10_000_000_000:
        ts = ts / 1000

    return datetime.fromtimestamp(ts, MARKET_TZ)


def _is_alert_from_market_today(normalized: dict) -> bool:
    alert = normalized.get("alert") or {}
    alert_dt = _timestamp_to_market_datetime(alert.get("timestamp"))

    if alert_dt is None:
        return False

    now = datetime.now(MARKET_TZ)
    return alert_dt.date() == now.date()


def _rejected_response(normalized: dict, reason: str) -> dict:
    return {
        "decision": "REJECT",
        "reason": reason,
        "classification": None,
        "marketContext": None,
        "strategyValidation": {
            "validator": None,
            "decision": "REJECT",
            "reason": reason,
            "checks": [],
            "failedChecks": [],
            "riskReward": None,
            "orderProposal": None,
        },
        "order": {
            "entry": None,
            "stopLoss": None,
            "takeProfit": None,
        },
        "normalized": normalized,
    }


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


def _attach_indicators(normalized: dict, classification: dict, market_context):
    if not isinstance(market_context, dict):
        return

    strategy = classification.get("strategy") if isinstance(classification, dict) else None
    if strategy != "ultra_short":
        return

    try:
        market_context["indicators"] = calculate_indicators(normalized, market_context)
    except Exception as exc:
        market_context["indicators"] = {}
        market_context["indicatorError"] = str(exc)


def _get_final_decision(strategy_validation: dict) -> tuple[str, str]:
    if isinstance(strategy_validation, dict):
        decision = strategy_validation.get("decision")
        reason = strategy_validation.get("reason")

        if decision in ("VALID", "REJECT", "SKIP", "WATCH"):
            return decision, reason or "Strategy validation completed"

    return "REJECT", "Strategy validation unavailable"


def analyze_normalized(normalized: dict):
    # TODO: Replace same-market-day guard with max age guard, e.g. alert age <= 10 minutes.
    if not _is_alert_from_market_today(normalized):
        return _rejected_response(normalized, "Alert is not from current US market day")

    classification = classify_alert(normalized)
    market_context = get_market_context(normalized, classification)
    _attach_indicators(normalized, classification, market_context)
    strategy_validation = validate_by_strategy(
        normalized,
        classification,
        market_context=market_context,
        ticker_context=_get_ticker_context(classification)
    )
    final_decision, final_reason = _get_final_decision(strategy_validation)

    return {
        "decision": final_decision,
        "reason": final_reason,
        "classification": classification,
        "marketContext": _serialize_market_context(market_context),
        "strategyValidation": strategy_validation,
        "order": {
            "entry": None,
            "stopLoss": None,
            "takeProfit": None
        }
    }
