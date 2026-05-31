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
            "symbol": option.get("symbol") or normalized.get("symbol"),
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
            "decision": "SKIP",
            "reason": "Invalid option symbol",
            "normalizedAlert": None,
            "classification": {},
            "marketContext": {},
            "indicators": {},
            "validation": {},
            "orderProposal": None,
            "pipeline": {
                "normalized": False,
                "classified": False,
                "marketDataAndIndicators": False,
                "validated": False,
                "orderProposalBuilt": False,
            },
        }

    classification = classify_normalized_alert(normalized)
    market_result = get_market_data_and_indicators(normalized, classification)
    indicators = market_result["indicators"]
    validation = validate_alert_contract(normalized, classification, indicators)

    order_proposal = None
    if validation.get("decision") == "VALID":
        order_request = _build_order_request(normalized, indicators)
        order_proposal = build_order_proposal(
            order_request["instrument"],
            order_request["entry"],
            order_request["exitRules"],
            order_request["risk"],
        )

    return {
        "status": "ok",
        "decision": validation.get("decision"),
        "reason": validation.get("reason"),
        "normalizedAlert": normalized,
        "classification": classification,
        "marketContext": market_result["marketContext"],
        "indicators": indicators,
        "validation": validation,
        "orderProposal": order_proposal,
        "pipeline": {
            "normalized": True,
            "classified": True,
            "marketDataAndIndicators": market_result.get("status") == "ok",
            "validated": validation.get("status") == "ok",
            "orderProposalBuilt": order_proposal is not None,
        },
    }
