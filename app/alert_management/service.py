from typing import Any, Dict

from app.alert_management.classification_service import classify_normalized_alert
from app.alert_management.market_service import get_market_data_and_indicators
from app.alert_management.order_service import build_order_proposal
from app.alert_management.validation_service import validate_alert_contract
from app.normalize import normalize_alert


DEFAULT_MAX_RISK_AMOUNT = 100


def _option(normalized: Dict[str, Any]) -> Dict[str, Any]:
    return normalized.get("option") or {}


def _underlying_symbol(normalized: Dict[str, Any]) -> Any:
    option = _option(normalized)
    return option.get("underlying") or normalized.get("underlying") or normalized.get("ticker")


def _build_order_request(normalized: Dict[str, Any], indicators: Dict[str, Any]) -> Dict[str, Any]:
    option = _option(normalized)
    option_indicators = indicators.get("option") or {}
    option_price = option_indicators.get("price") or {}
    move_estimates = option_indicators.get("moveEstimates") or {}
    underlying = indicators.get("underlying") or {}
    trigger_symbol = _underlying_symbol(normalized)

    return {
        "instrument": {
            "assetType": "OPTION",
            "symbol": normalized.get("symbol") or option.get("symbol"),
            "action": "BUY",
            "multiplier": 100,
        },
        "entry": {
            "price": option_price.get("ask"),
            "orderType": "LMT",
            "priceSource": "option_ask",
        },
        "exitRules": {
            "stop": {
                "triggerType": "UNDERLYING_PRICE",
                "triggerSymbol": trigger_symbol,
                "triggerPrice": underlying.get("stop"),
                "estimatedInstrumentPrice": move_estimates.get("estimatedOptionPriceAtStop"),
            },
            "target": {
                "triggerType": "UNDERLYING_PRICE",
                "triggerSymbol": trigger_symbol,
                "triggerPrice": underlying.get("target"),
                "estimatedInstrumentPrice": move_estimates.get("estimatedOptionPriceAtTarget"),
            },
        },
        "risk": {
            "maxRiskAmount": DEFAULT_MAX_RISK_AMOUNT,
            "model": {
                "estimatedLossPerUnit": move_estimates.get("estimatedOptionLossToStop"),
                "estimatedLossPerContract": move_estimates.get("estimatedLossPerContract"),
                "estimatedRewardPerContract": move_estimates.get("estimatedRewardPerContract"),
                "estimatedRiskReward": move_estimates.get("estimatedRiskReward"),
            },
        },
    }


def manage_alert(raw_alert: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_alert(raw_alert)
    if normalized is None:
        return {
            "status": "error",
            "classification": {},
            "marketDataAndIndicators": {},
            "validation": {
                "status": "error",
                "decision": "SKIP",
                "reason": "Invalid option symbol",
                "checks": {},
            },
            "orderProposal": None,
        }

    classification_response = classify_normalized_alert(normalized)
    market_data_and_indicators_response = get_market_data_and_indicators(
        normalized,
        classification_response,
    )
    indicators = market_data_and_indicators_response.get("indicators") or {}
    validation_response = validate_alert_contract(
        normalized,
        classification_response,
        indicators,
    )

    order_proposal = None
    if validation_response.get("decision") == "VALID":
        order_request = _build_order_request(normalized, indicators)
        order_proposal = build_order_proposal(
            order_request["instrument"],
            order_request["entry"],
            order_request["exitRules"],
            order_request["risk"],
        )

    return {
        "status": "ok",
        "classification": classification_response,
        "marketDataAndIndicators": market_data_and_indicators_response,
        "validation": validation_response,
        "orderProposal": order_proposal,
    }
