import math
from typing import Any, Dict, Optional


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _sizing_unit(asset_type: str, model: Dict[str, Any]) -> Optional[float]:
    if asset_type == "OPTION":
        return _safe_float(model.get("estimatedLossPerContract"))
    if asset_type == "STOCK":
        return _safe_float(model.get("estimatedLossPerUnit"))
    return None


def _multiplier(asset_type: str, instrument: Dict[str, Any]) -> int:
    if asset_type == "OPTION":
        return int(instrument.get("multiplier") or 100)
    return 1


def build_order_proposal(
    instrument: Dict[str, Any],
    entry: Dict[str, Any],
    exit_rules: Dict[str, Any],
    risk: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    asset_type = (instrument.get("assetType") or "").upper()
    symbol = instrument.get("symbol")
    action = instrument.get("action")
    entry_price = _safe_float(entry.get("price"))
    max_risk_amount = _safe_float(risk.get("maxRiskAmount"))
    model = risk.get("model") or {}
    sizing_unit = _sizing_unit(asset_type, model)

    if (
        asset_type not in ("OPTION", "STOCK")
        or not symbol
        or not action
        or entry_price is None
        or max_risk_amount is None
        or max_risk_amount <= 0
        or sizing_unit is None
        or sizing_unit <= 0
    ):
        return None

    quantity = math.floor(max_risk_amount / sizing_unit)
    if quantity < 1:
        return None

    estimated_loss_per_unit = _safe_float(model.get("estimatedLossPerUnit"))
    estimated_loss_per_contract = _safe_float(model.get("estimatedLossPerContract"))
    estimated_reward_per_contract = _safe_float(model.get("estimatedRewardPerContract"))
    estimated_risk_reward = _safe_float(model.get("estimatedRiskReward"))

    return {
        "action": action,
        "assetType": asset_type,
        "symbol": symbol,
        "quantity": quantity,
        "entryOrder": {
            "orderType": entry.get("orderType"),
            "limitPrice": entry_price,
            "priceSource": entry.get("priceSource"),
        },
        "risk": {
            "maxRiskAmount": max_risk_amount,
            "estimatedLossPerUnit": estimated_loss_per_unit,
            "estimatedLossPerContract": estimated_loss_per_contract,
            "estimatedTotalRisk": sizing_unit * quantity,
        },
        "reward": {
            "estimatedRewardPerContract": estimated_reward_per_contract,
            "estimatedTotalReward": (
                estimated_reward_per_contract * quantity
                if estimated_reward_per_contract is not None
                else None
            ),
            "estimatedRiskReward": estimated_risk_reward,
        },
        "exitRules": exit_rules,
        "sizingMethod": "max_risk_divided_by_estimated_loss",
        "multiplier": _multiplier(asset_type, instrument),
    }
