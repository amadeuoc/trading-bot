from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class OptionMarketData(BaseModel):
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    implied_volatility: Optional[float] = None


class UnderlyingMarketData(BaseModel):
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None


class MarketIndicators(BaseModel):
    spread_pct: Optional[float] = None
    liquidity_score: Optional[float] = None
    risk_reward: Optional[float] = None
    rsi14: Optional[float] = None
    atr14: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    momentum: Optional[float] = None
    williams_r: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    implied_volatility: Optional[float] = None
    historical_volatility: Optional[float] = None
    iv_hv_ratio: Optional[float] = None


class OptionGexPoint(BaseModel):
    expiry: Optional[str] = None
    dte: Optional[int] = None
    strike: float
    option_type: Literal["CALL", "PUT"]
    gamma: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    oi_gex: Optional[float] = None
    volume_gex: Optional[float] = None
    hybrid_gex: Optional[float] = None
    signed_flow_gex: Optional[float] = None
    aggressor: Optional[Literal["buyer", "seller", "unknown"]] = None


class GexWallContext(BaseModel):
    strike: float
    option_type: Literal["CALL", "PUT"]
    position: Literal["above", "below", "at_spot"]
    distance_from_spot: Optional[float] = None
    distance_pct_from_spot: Optional[float] = None
    oi_gex: Optional[float] = None
    volume_gex: Optional[float] = None
    hybrid_gex: Optional[float] = None
    hybrid_strength: Optional[float] = None
    signed_flow_gex_total: Optional[float] = None
    sign: Literal["positive", "negative", "mixed", "unknown"]
    sign_score: Optional[float] = None
    behavior: Literal[
        "resistance",
        "support",
        "breakout_accelerator",
        "breakdown_accelerator",
        "mixed",
        "unknown"
    ]


class GexContext(BaseModel):
    source: str
    spot: Optional[float] = None
    dte_max: Optional[int] = None
    range_pct: Optional[float] = None
    points: List[OptionGexPoint] = Field(default_factory=list)
    walls: List[GexWallContext] = Field(default_factory=list)
    strongest_wall_above: Optional[GexWallContext] = None
    strongest_wall_below: Optional[GexWallContext] = None
    strongest_call_wall: Optional[GexWallContext] = None
    strongest_put_wall: Optional[GexWallContext] = None


class MarketContext(BaseModel):
    option: Optional[OptionMarketData] = None
    underlying: Optional[UnderlyingMarketData] = None
    indicators: Optional[MarketIndicators] = None
    gex_context: Optional[GexContext] = None
