from typing import Optional


MOVE_ESTIMATE_METHOD = "delta_gamma_spread_buffer"
MOVE_ESTIMATE_SAFETY_MULTIPLIER = 1.2


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def estimate_option_move_from_underlying_levels(
    *,
    bid,
    ask,
    delta,
    gamma,
    underlying_entry,
    underlying_stop,
    underlying_target,
    safety_multiplier=MOVE_ESTIMATE_SAFETY_MULTIPLIER,
):
    delta = _safe_float(delta)
    gamma = _safe_float(gamma)
    bid = _safe_float(bid)
    ask = _safe_float(ask)
    entry = _safe_float(underlying_entry)
    stop = _safe_float(underlying_stop)
    target = _safe_float(underlying_target)
    safety_multiplier = _safe_float(safety_multiplier)

    if None in (delta, gamma, bid, ask, entry, stop, target, safety_multiplier):
        return None
    if bid <= 0 or ask <= 0:
        return None

    stop_distance = abs(entry - stop)
    target_distance = abs(target - entry)
    spread = ask - bid

    estimated_loss = (
        abs(delta) * stop_distance
        + 0.5 * abs(gamma) * stop_distance ** 2
        + spread * 0.5
    ) * safety_multiplier

    estimated_gain = (
        abs(delta) * target_distance
        + 0.5 * abs(gamma) * target_distance ** 2
        - spread * 0.5
    )

    estimated_loss_per_contract = estimated_loss * 100
    estimated_reward_per_contract = estimated_gain * 100

    return {
        "method": MOVE_ESTIMATE_METHOD,
        "safetyMultiplier": safety_multiplier,
        "estimatedOptionLossToStop": estimated_loss,
        "estimatedOptionGainToTarget": estimated_gain,
        "estimatedOptionPriceAtStop": max(0.01, ask - estimated_loss),
        "estimatedOptionPriceAtTarget": max(0.01, ask + estimated_gain),
        "estimatedLossPerContract": estimated_loss_per_contract,
        "estimatedRewardPerContract": estimated_reward_per_contract,
        "estimatedRiskReward": (
            estimated_reward_per_contract / estimated_loss_per_contract
            if estimated_loss_per_contract > 0
            else None
        ),
    }
