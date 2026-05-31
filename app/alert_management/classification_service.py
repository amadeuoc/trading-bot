from typing import Any, Dict

from app.classify import classify_alert


def classify_normalized_alert(normalized_alert: Dict[str, Any]) -> Dict[str, Any]:
    return classify_alert(normalized_alert)
