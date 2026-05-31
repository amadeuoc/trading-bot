from fastapi import APIRouter

from app.alert_management.classification_service import classify_normalized_alert
from app.alert_management.market_service import get_market_data_and_indicators
from app.alert_management.order_service import build_order_proposal
from app.alert_management.schemas import (
    BuildOrderProposalRequest,
    ClassifyAlertRequest,
    ManageAlertRequest,
    MarketDataAndIndicatorsRequest,
    ValidateAlertRequest,
)
from app.alert_management.service import manage_alert
from app.alert_management.validation_service import validate_alert_contract


router = APIRouter()


def _model_to_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@router.post("/manageAlert")
def manage_alert_endpoint(req: ManageAlertRequest):
    return manage_alert(req.rawAlert)


@router.post("/classifyAlert")
def classify_alert_endpoint(req: ClassifyAlertRequest):
    return {
        "classification": classify_normalized_alert(req.normalizedAlert)
    }


@router.post("/getMarketDataAndIndicators")
def market_data_and_indicators_endpoint(req: MarketDataAndIndicatorsRequest):
    return get_market_data_and_indicators(
        req.normalizedAlert,
        req.classification,
    )


@router.post("/validateAlert")
def validate_alert_endpoint(req: ValidateAlertRequest):
    return validate_alert_contract(
        req.normalizedAlert,
        req.classification,
        req.indicators,
    )


@router.post("/buildOrderProposal")
def build_order_proposal_endpoint(req: BuildOrderProposalRequest):
    return {
        "status": "ok",
        "orderProposal": build_order_proposal(
            req.normalizedAlert,
            _model_to_dict(req.orderInputs),
        ),
    }
