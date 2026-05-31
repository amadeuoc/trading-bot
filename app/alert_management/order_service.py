from typing import Any, Dict, Optional


def build_order_proposal(
    normalized_alert: Dict[str, Any],
    order_inputs: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    entry = order_inputs.get("entry")
    stop = order_inputs.get("stop")
    target = order_inputs.get("target")

    if entry is None or stop is None or target is None:
        return None

    return {
        "entry": entry,
        "stopLoss": stop,
        "takeProfit": target,
        "riskReward": order_inputs.get("riskReward"),
        "riskTolerance": order_inputs.get("riskTolerance") or {},
        "selectedWallAbove": order_inputs.get("selectedWallAbove"),
        "selectedWallBelow": order_inputs.get("selectedWallBelow"),
        "contract": normalized_alert.get("option") or {},
    }
