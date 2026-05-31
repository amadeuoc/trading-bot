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


class RiskTolerance(BaseModel):
    maxLossUsd: Optional[float] = None


class OrderInputs(BaseModel):
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    riskReward: Optional[float] = None
    riskTolerance: RiskTolerance = Field(default_factory=RiskTolerance)
    selectedWallAbove: Optional[Dict[str, Any]] = None
    selectedWallBelow: Optional[Dict[str, Any]] = None


class BuildOrderProposalRequest(BaseModel):
    normalizedAlert: Dict[str, Any] = Field(default_factory=dict)
    orderInputs: OrderInputs = Field(default_factory=OrderInputs)
