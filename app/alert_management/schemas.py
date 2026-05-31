from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ManageAlertRequest(BaseModel):
    rawAlert: Dict[str, Any] = Field(default_factory=dict)


class ClassifyAlertRequest(BaseModel):
    normalizedAlert: Dict[str, Any] = Field(default_factory=dict)


class MarketDataAndIndicatorsRequest(BaseModel):
    normalizedAlert: Dict[str, Any] = Field(default_factory=dict)
    classification: Dict[str, Any] = Field(default_factory=dict)


class ValidateAlertRequest(BaseModel):
    normalizedAlert: Dict[str, Any] = Field(default_factory=dict)
    classification: Dict[str, Any] = Field(default_factory=dict)
    indicators: Dict[str, Any] = Field(default_factory=dict)


class Instrument(BaseModel):
    assetType: Optional[str] = None
    symbol: Optional[str] = None
    action: Optional[str] = None
    multiplier: Optional[int] = None


class Entry(BaseModel):
    price: Optional[float] = None
    orderType: Optional[str] = None
    priceSource: Optional[str] = None


class ExitRule(BaseModel):
    triggerType: Optional[str] = None
    triggerSymbol: Optional[str] = None
    triggerPrice: Optional[float] = None
    estimatedInstrumentPrice: Optional[float] = None


class ExitRules(BaseModel):
    stop: ExitRule = Field(default_factory=ExitRule)
    target: ExitRule = Field(default_factory=ExitRule)


class RiskModel(BaseModel):
    estimatedLossPerUnit: Optional[float] = None
    estimatedLossPerContract: Optional[float] = None
    estimatedRewardPerContract: Optional[float] = None
    estimatedRiskReward: Optional[float] = None


class Risk(BaseModel):
    maxRiskAmount: Optional[float] = None
    model: RiskModel = Field(default_factory=RiskModel)


class BuildOrderProposalRequest(BaseModel):
    instrument: Instrument = Field(default_factory=Instrument)
    entry: Entry = Field(default_factory=Entry)
    exitRules: ExitRules = Field(default_factory=ExitRules)
    risk: Risk = Field(default_factory=Risk)
