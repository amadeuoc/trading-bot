from typing import Optional

from pydantic import BaseModel


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


class MarketContext(BaseModel):
    option: Optional[OptionMarketData] = None
    underlying: Optional[UnderlyingMarketData] = None
    indicators: Optional[MarketIndicators] = None
