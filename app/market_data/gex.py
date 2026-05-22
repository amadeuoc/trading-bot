from pathlib import Path
import sys
from typing import Any, Dict, List, Literal, Optional, Tuple

try:
    from app.market_data.models import GexContext, GexWallContext, OptionGexPoint
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from app.market_data.models import GexContext, GexWallContext, OptionGexPoint


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def compute_oi_gex(gamma, open_interest, spot, multiplier=100) -> Optional[float]:
    gamma = _safe_float(gamma)
    open_interest = _safe_float(open_interest)
    spot = _safe_float(spot)

    if gamma is None or open_interest is None or spot is None:
        return None

    return gamma * open_interest * multiplier * spot ** 2 * 0.01


def compute_volume_gex(gamma, volume, spot, multiplier=100) -> Optional[float]:
    gamma = _safe_float(gamma)
    volume = _safe_float(volume)
    spot = _safe_float(spot)

    if gamma is None or volume is None or spot is None:
        return None

    return gamma * volume * multiplier * spot ** 2 * 0.01


def compute_hybrid_gex(
    oi_gex,
    volume_gex,
    oi_weight=0.30,
    volume_weight=0.70
) -> float:
    oi_value = _safe_float(oi_gex) or 0
    volume_value = _safe_float(volume_gex) or 0
    return (oi_weight * oi_value) + (volume_weight * volume_value)


def compute_target_buffer(spot) -> Optional[float]:
    spot = _safe_float(spot)
    if spot is None or spot <= 0:
        return None
    return max(spot * 0.0010, 0.01)


def compute_stop_buffer(spot) -> Optional[float]:
    spot = _safe_float(spot)
    if spot is None or spot <= 0:
        return None
    return max(spot * 0.0020, 0.02)


def infer_aggressor(bid, ask, last) -> Literal["buyer", "seller", "unknown"]:
    bid = _safe_float(bid)
    ask = _safe_float(ask)
    last = _safe_float(last)

    if bid is None or ask is None or last is None:
        return "unknown"
    if bid <= 0 or ask <= 0 or ask <= bid:
        return "unknown"
    if last >= ask * 0.995:
        return "buyer"
    if last <= bid * 1.005:
        return "seller"
    return "unknown"


def compute_signed_flow_gex(volume_gex, aggressor) -> Optional[float]:
    volume_gex = _safe_float(volume_gex)

    if volume_gex is None:
        return None
    if aggressor == "buyer":
        return -volume_gex
    if aggressor == "seller":
        return volume_gex
    return None


def build_option_gex_points(
    raw_options: List[dict],
    spot,
    strategy="ultra_short",
    dte_max=None
) -> List[OptionGexPoint]:
    points = []

    for raw in raw_options or []:
        dte = _safe_int(raw.get("dte"))
        if dte_max is not None and dte is not None and dte > dte_max:
            continue

        strike = _safe_float(raw.get("strike"))
        option_type = raw.get("option_type") or raw.get("type")
        if strike is None or option_type not in ("CALL", "PUT"):
            continue

        gamma = _safe_float(raw.get("gamma"))
        open_interest = _safe_int(raw.get("open_interest", raw.get("openInterest")))
        volume = _safe_int(raw.get("volume"))
        bid = _safe_float(raw.get("bid"))
        ask = _safe_float(raw.get("ask"))
        last = _safe_float(raw.get("last"))

        oi_gex = compute_oi_gex(gamma, open_interest, spot)
        volume_gex = compute_volume_gex(gamma, volume, spot)
        oi_weight = 0.30 if strategy == "ultra_short" else 0.30
        volume_weight = 0.70 if strategy == "ultra_short" else 0.70
        hybrid_gex = compute_hybrid_gex(
            oi_gex,
            volume_gex,
            oi_weight=oi_weight,
            volume_weight=volume_weight
        )
        aggressor = infer_aggressor(bid, ask, last)
        signed_flow_gex = compute_signed_flow_gex(volume_gex, aggressor)

        points.append(OptionGexPoint(
            expiry=raw.get("expiry"),
            dte=dte,
            strike=strike,
            option_type=option_type,
            gamma=gamma,
            open_interest=open_interest,
            volume=volume,
            bid=bid,
            ask=ask,
            last=last,
            oi_gex=oi_gex,
            volume_gex=volume_gex,
            hybrid_gex=hybrid_gex,
            signed_flow_gex=signed_flow_gex,
            aggressor=aggressor
        ))

    return points


def _point_value(point: OptionGexPoint, field: str) -> float:
    return _safe_float(getattr(point, field, None)) or 0


def _position_for_strike(strike: float, spot: float) -> Literal["above", "below", "at_spot"]:
    if strike > spot:
        return "above"
    if strike < spot:
        return "below"
    return "at_spot"


def compute_wall_sign_from_net_gex(
    net_hybrid_gex,
    hybrid_strength
) -> Tuple[Literal["positive", "negative", "mixed", "unknown"], Optional[float]]:
    net_hybrid_gex = _safe_float(net_hybrid_gex)
    hybrid_strength = _safe_float(hybrid_strength)

    if net_hybrid_gex is None or hybrid_strength is None or hybrid_strength <= 0:
        return "unknown", None

    score = net_hybrid_gex / hybrid_strength
    if score >= 0.30:
        return "positive", score
    if score <= -0.30:
        return "negative", score
    return "mixed", score


def determine_wall_behavior(position, sign):
    if sign == "unknown":
        return "unknown"
    if sign == "mixed":
        return "mixed"
    if position == "at_spot":
        return "mixed"
    if position == "above" and sign == "positive":
        return "resistance"
    if position == "below" and sign == "positive":
        return "support"
    if position == "above" and sign == "negative":
        return "breakout_accelerator"
    if position == "below" and sign == "negative":
        return "breakdown_accelerator"
    return "unknown"


def build_gex_walls(
    points: List[OptionGexPoint],
    spot,
    range_pct=0.03,
    min_hybrid_gex=None
) -> List[GexWallContext]:
    spot = _safe_float(spot)
    if spot is None or spot <= 0:
        return []

    groups: Dict[float, List[OptionGexPoint]] = {}
    for point in points or []:
        if point.strike is None:
            continue

        if range_pct is not None:
            distance_pct = abs(point.strike - spot) / spot
            if distance_pct > range_pct:
                continue

        groups.setdefault(point.strike, []).append(point)

    walls = []
    for strike, group in groups.items():
        call_hybrid_gex = sum(
            _point_value(point, "hybrid_gex")
            for point in group
            if point.option_type == "CALL"
        )
        put_hybrid_gex = sum(
            _point_value(point, "hybrid_gex")
            for point in group
            if point.option_type == "PUT"
        )
        net_hybrid_gex = call_hybrid_gex - put_hybrid_gex
        call_strength = abs(call_hybrid_gex)
        put_strength = abs(put_hybrid_gex)
        hybrid_strength = call_strength + put_strength

        if call_strength > put_strength:
            dominant_side = "CALL"
        elif put_strength > call_strength:
            dominant_side = "PUT"
        elif hybrid_strength > 0:
            dominant_side = "mixed"
        else:
            dominant_side = "unknown"

        oi_gex = sum(_point_value(point, "oi_gex") for point in group)
        volume_gex = sum(_point_value(point, "volume_gex") for point in group)
        hybrid_gex = net_hybrid_gex

        if min_hybrid_gex is not None and hybrid_strength < min_hybrid_gex:
            continue

        position = _position_for_strike(strike, spot)
        sign, sign_score = compute_wall_sign_from_net_gex(
            net_hybrid_gex,
            hybrid_strength
        )
        signed_total = sum(
            _point_value(point, "signed_flow_gex")
            for point in group
            if point.signed_flow_gex is not None
        )
        behavior = determine_wall_behavior(position, sign)

        walls.append(GexWallContext(
            strike=strike,
            dominant_side=dominant_side,
            position=position,
            distance_from_spot=strike - spot,
            distance_pct_from_spot=abs(strike - spot) / spot * 100,
            call_hybrid_gex=call_hybrid_gex,
            put_hybrid_gex=put_hybrid_gex,
            net_hybrid_gex=net_hybrid_gex,
            call_strength=call_strength,
            put_strength=put_strength,
            oi_gex=oi_gex,
            volume_gex=volume_gex,
            hybrid_gex=hybrid_gex,
            hybrid_strength=hybrid_strength,
            signed_flow_gex_total=signed_total,
            sign=sign,
            sign_score=sign_score,
            behavior=behavior
        ))

    return walls


def _wall_strength(wall: GexWallContext) -> float:
    if wall.hybrid_strength is not None:
        return wall.hybrid_strength
    if wall.hybrid_gex is not None:
        return abs(wall.hybrid_gex)
    return 0


def _significant_walls(walls):
    return [wall for wall in walls if _wall_strength(wall) > 0]


def _trade_walls(walls):
    return [
        wall for wall in _significant_walls(walls)
        if wall.behavior in ("support", "resistance")
    ]


def _nearest(walls, position):
    candidates = [
        wall for wall in _significant_walls(walls)
        if wall.position == position
    ]
    return min(
        candidates,
        key=lambda wall: abs(wall.distance_from_spot or 0)
    ) if candidates else None


def _strongest(walls):
    candidates = _significant_walls(walls)
    return max(candidates, key=_wall_strength) if candidates else None


def find_nearest_above(walls):
    return _nearest(walls, "above")


def find_nearest_below(walls):
    return _nearest(walls, "below")


def find_strongest_wall_above(walls):
    return _strongest([wall for wall in walls if wall.position == "above"])


def find_strongest_wall_below(walls):
    return _strongest([wall for wall in walls if wall.position == "below"])


def find_nearest_trade_wall_above(walls):
    return _nearest(_trade_walls(walls), "above")


def find_nearest_trade_wall_below(walls):
    return _nearest(_trade_walls(walls), "below")


def find_strongest_trade_wall_above(walls):
    return _strongest([
        wall for wall in _trade_walls(walls)
        if wall.position == "above"
    ])


def find_strongest_trade_wall_below(walls):
    return _strongest([
        wall for wall in _trade_walls(walls)
        if wall.position == "below"
    ])


def find_strongest_call_wall(walls):
    return _strongest([wall for wall in walls if wall.dominant_side == "CALL"])


def find_strongest_put_wall(walls):
    return _strongest([wall for wall in walls if wall.dominant_side == "PUT"])


def build_gex_context(
    raw_options,
    spot,
    dte_max=None,
    range_pct=0.03,
    source="ibkr_placeholder"
) -> GexContext:
    points = build_option_gex_points(
        raw_options,
        spot,
        strategy="ultra_short",
        dte_max=dte_max
    )
    walls = build_gex_walls(points, spot, range_pct=range_pct)

    return GexContext(
        source=source,
        spot=_safe_float(spot),
        dte_max=dte_max,
        range_pct=range_pct,
        points=points,
        walls=walls,
        nearest_above=find_nearest_above(walls),
        nearest_below=find_nearest_below(walls),
        strongest_wall_above=find_strongest_wall_above(walls),
        strongest_wall_below=find_strongest_wall_below(walls),
        nearest_trade_wall_above=find_nearest_trade_wall_above(walls),
        nearest_trade_wall_below=find_nearest_trade_wall_below(walls),
        strongest_trade_wall_above=find_strongest_trade_wall_above(walls),
        strongest_trade_wall_below=find_strongest_trade_wall_below(walls),
        strongest_call_wall=find_strongest_call_wall(walls),
        strongest_put_wall=find_strongest_put_wall(walls)
    )


def _dump_model(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


if __name__ == "__main__":
    sample_options = [
        {
            "expiry": "2026-05-15",
            "dte": 0,
            "strike": 101,
            "option_type": "CALL",
            "gamma": 0.02,
            "open_interest": 1000,
            "volume": 5000,
            "bid": 1.0,
            "ask": 1.1,
            "last": 1.1
        },
        {
            "expiry": "2026-05-15",
            "dte": 0,
            "strike": 99,
            "option_type": "PUT",
            "gamma": 0.03,
            "open_interest": 1500,
            "volume": 3000,
            "bid": 1.2,
            "ask": 1.4,
            "last": 1.2
        },
        {
            "expiry": "2026-05-15",
            "dte": 0,
            "strike": 101,
            "option_type": "PUT",
            "gamma": 0.01,
            "open_interest": 500,
            "volume": 1000,
            "bid": 0.5,
            "ask": 0.6,
            "last": 0.55
        },
        {
            "expiry": "2026-05-15",
            "dte": 0,
            "strike": 99,
            "option_type": "CALL",
            "gamma": 0.015,
            "open_interest": 800,
            "volume": 1200,
            "bid": 0.7,
            "ask": 0.8,
            "last": 0.8
        },
    ]
    context = build_gex_context(sample_options, 100, dte_max=0, range_pct=0.03)
    print("gex_context", context.model_dump())
