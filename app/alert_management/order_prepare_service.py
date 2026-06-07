from datetime import datetime
import math
from typing import Any, Dict, Optional

from app.alert_management.order_service import build_order_proposal
from app.market_data.option_estimates import estimate_option_move_from_underlying_levels
from app.market_data.option_market_snapshot import get_option_market_snapshot


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _is_positive(value) -> bool:
    value = _safe_float(value)
    return value is not None and value > 0


def _normalize_asset_type(value) -> str:
    return str(value or "").upper()


def _normalize_action(value) -> str:
    return str(value or "").upper()


def _normalize_right(value) -> str:
    return str(value or "").upper()


def _valid_expiration(value) -> bool:
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def _common_rejection_reason(request: Dict[str, Any]) -> Optional[str]:
    target = request.get("target") or {}
    stop = request.get("stop") or {}

    if _normalize_action(request.get("action")) != "BUY":
        return "Unsupported action, only BUY is supported"
    if not request.get("ticker"):
        return "Missing or invalid ticker"
    if not _is_positive(request.get("entryPrice")):
        return "entryPrice must be greater than 0"
    if not _is_positive(stop.get("price")):
        return "stop.price must be greater than 0"
    if not _is_positive(target.get("price")):
        return "target.price must be greater than 0"
    if not _is_positive(request.get("maxRiskAmount")):
        return "maxRiskAmount must be greater than 0"
    if str(target.get("mode") or "").upper() != "FIXED":
        return "target.mode must be FIXED"

    return None


def _risk_reward(reward, loss) -> Optional[float]:
    reward = _safe_float(reward)
    loss = _safe_float(loss)
    if reward is None or loss is None or loss <= 0:
        return None
    return reward / loss


def _prepare_stock_order(request: Dict[str, Any]):
    reason = _common_rejection_reason(request)
    if reason:
        return None, reason

    ticker = str(request.get("ticker")).upper()
    entry_price = _safe_float(request.get("entryPrice"))
    max_risk_amount = _safe_float(request.get("maxRiskAmount"))
    stop = request.get("stop") or {}
    target = request.get("target") or {}
    stop_price = _safe_float(stop.get("price"))
    target_price = _safe_float(target.get("price"))

    if str(stop.get("type") or "").upper() != "INSTRUMENT_PRICE":
        return None, "For STOCK BUY, stop.type must be INSTRUMENT_PRICE"
    if str(target.get("type") or "").upper() != "INSTRUMENT_PRICE":
        return None, "For STOCK BUY, target.type must be INSTRUMENT_PRICE"
    if stop_price is None or target_price is None or entry_price is None:
        return None, "Missing or invalid STOCK price input"
    if stop_price >= entry_price or target_price <= entry_price:
        if stop_price >= entry_price:
            return None, "For STOCK BUY, stop price must be below entry price"
        return None, "For STOCK BUY, target price must be above entry price"

    estimated_loss_per_unit = entry_price - stop_price
    estimated_reward_per_contract = target_price - entry_price
    estimated_risk_reward = _risk_reward(
        estimated_reward_per_contract,
        estimated_loss_per_unit,
    )

    order_proposal = build_order_proposal(
        {
            "assetType": "STOCK",
            "symbol": ticker,
            "action": "BUY",
            "multiplier": 1,
        },
        {
            "price": entry_price,
            "orderType": "LMT",
            "priceSource": "manual",
        },
        {
            "stop": {
                "triggerType": "INSTRUMENT_PRICE",
                "triggerSymbol": ticker,
                "triggerPrice": stop_price,
                "estimatedInstrumentPrice": stop_price,
            },
            "target": {
                "triggerType": "INSTRUMENT_PRICE",
                "triggerSymbol": ticker,
                "triggerPrice": target_price,
                "estimatedInstrumentPrice": target_price,
            },
        },
        {
            "maxRiskAmount": max_risk_amount,
            "model": {
                "estimatedLossPerUnit": estimated_loss_per_unit,
                "estimatedLossPerContract": estimated_loss_per_unit,
                "estimatedRewardPerContract": estimated_reward_per_contract,
                "estimatedRiskReward": estimated_risk_reward,
            },
        },
    )
    if order_proposal is None:
        return None, "Unable to build STOCK order proposal"
    return order_proposal, None


def _option_direction_is_valid(right, underlying_price, stop_price, target_price) -> bool:
    if underlying_price is None:
        return True
    if right == "CALL":
        return stop_price < underlying_price and target_price > underlying_price
    if right == "PUT":
        return stop_price > underlying_price and target_price < underlying_price
    return False


def _prepare_option_order(request: Dict[str, Any]):
    reason = _common_rejection_reason(request)
    if reason:
        return None, reason

    ticker = str(request.get("ticker")).upper()
    entry_price = _safe_float(request.get("entryPrice"))
    max_risk_amount = _safe_float(request.get("maxRiskAmount"))
    stop = request.get("stop") or {}
    target = request.get("target") or {}
    option = request.get("option") or {}
    right = _normalize_right(option.get("right"))
    strike = _safe_float(option.get("strike"))
    expiration = option.get("expiration")
    stop_price = _safe_float(stop.get("price"))
    target_price = _safe_float(target.get("price"))

    if right not in ("CALL", "PUT"):
        return None, "option.right must be CALL or PUT"
    if strike is None or strike <= 0:
        return None, "option.strike must be greater than 0"
    if not _valid_expiration(expiration):
        return None, "option.expiration must be a valid YYYY-MM-DD date"
    if str(stop.get("type") or "").upper() != "UNDERLYING_PRICE":
        return None, "For OPTION BUY, stop.type must be UNDERLYING_PRICE"
    if str(target.get("type") or "").upper() != "UNDERLYING_PRICE":
        return None, "For OPTION BUY, target.type must be UNDERLYING_PRICE"
    if None in (entry_price, max_risk_amount, stop_price, target_price):
        return None, "Missing or invalid OPTION price input"

    snapshot = get_option_market_snapshot(
        ticker=ticker,
        right=right,
        expiration=expiration,
        strike=strike,
    )
    if not snapshot:
        return None, "Unable to fetch market snapshot from IBKR"

    underlying = snapshot.get("underlying") or {}
    option_snapshot = snapshot.get("option") or {}
    underlying_price = _safe_float(underlying.get("price"))
    if not _option_direction_is_valid(right, underlying_price, stop_price, target_price):
        return None, f"Invalid {right} stop/target direction versus current underlying price"

    estimates = estimate_option_move_from_underlying_levels(
        bid=option_snapshot.get("bid"),
        ask=option_snapshot.get("ask"),
        delta=option_snapshot.get("delta"),
        gamma=option_snapshot.get("gamma"),
        underlying_entry=underlying_price,
        underlying_stop=stop_price,
        underlying_target=target_price,
    )
    if not estimates:
        return None, "Unable to estimate option move because bid/ask/delta/gamma are missing"

    estimated_stop_price = _safe_float(estimates.get("estimatedOptionPriceAtStop"))
    estimated_target_price = _safe_float(estimates.get("estimatedOptionPriceAtTarget"))
    if estimated_stop_price is None or estimated_target_price is None:
        return None, "Unable to estimate option stop/target prices"
    if estimated_stop_price >= entry_price:
        return None, "Estimated stop option price must be below entryPrice"
    if estimated_target_price <= entry_price:
        return None, "Estimated target option price must be above entryPrice"

    estimated_loss_per_unit = entry_price - estimated_stop_price
    estimated_loss_per_contract = estimated_loss_per_unit * 100
    estimated_reward_per_contract = (estimated_target_price - entry_price) * 100
    estimated_risk_reward = _risk_reward(
        estimated_reward_per_contract,
        estimated_loss_per_contract,
    )
    if estimated_loss_per_contract <= 0:
        return None, "Estimated loss per contract must be greater than 0"

    order_proposal = build_order_proposal(
        {
            "assetType": "OPTION",
            "symbol": option_snapshot.get("symbol"),
            "action": "BUY",
            "multiplier": 100,
        },
        {
            "price": entry_price,
            "orderType": "LMT",
            "priceSource": "manual",
        },
        {
            "stop": {
                "triggerType": "UNDERLYING_PRICE",
                "triggerSymbol": ticker,
                "triggerPrice": stop_price,
                "estimatedInstrumentPrice": estimated_stop_price,
            },
            "target": {
                "triggerType": "UNDERLYING_PRICE",
                "triggerSymbol": ticker,
                "triggerPrice": target_price,
                "estimatedInstrumentPrice": estimated_target_price,
            },
        },
        {
            "maxRiskAmount": max_risk_amount,
            "model": {
                "estimatedLossPerUnit": estimated_loss_per_unit,
                "estimatedLossPerContract": estimated_loss_per_contract,
                "estimatedRewardPerContract": estimated_reward_per_contract,
                "estimatedRiskReward": estimated_risk_reward,
            },
        },
    )
    if order_proposal is None:
        return None, "Unable to build OPTION order proposal"
    return order_proposal, None


def prepare_order(request: Dict[str, Any]) -> Dict[str, Any]:
    asset_type = _normalize_asset_type(request.get("assetType"))

    if asset_type == "STOCK":
        order_proposal, reason = _prepare_stock_order(request)
    elif asset_type == "OPTION":
        order_proposal, reason = _prepare_option_order(request)
    else:
        order_proposal = None
        reason = "assetType must be STOCK or OPTION"

    return {
        "status": "ok" if order_proposal is not None else "rejected",
        "reason": None if order_proposal is not None else reason,
        "orderProposal": order_proposal,
    }
