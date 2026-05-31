from typing import Any, Dict

from app.alert_management.classification_service import classify_normalized_alert
from app.alert_management.market_service import get_market_data_and_indicators
from app.alert_management.order_service import build_order_proposal
from app.alert_management.validation_service import validate_alert_contract
from app.normalize import normalize_alert


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
        order_proposal = build_order_proposal(
            normalized,
            {
                "entry": indicators.get("entry"),
                "stop": indicators.get("stop"),
                "target": indicators.get("target"),
                "riskReward": indicators.get("riskReward"),
                "riskTolerance": {"maxLossUsd": None},
                "selectedWallAbove": (indicators.get("gex") or {}).get("walls", {}).get("selectedWallAbove"),
                "selectedWallBelow": (indicators.get("gex") or {}).get("walls", {}).get("selectedWallBelow"),
            },
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
