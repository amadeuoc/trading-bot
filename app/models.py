from pydantic import BaseModel
from typing import Dict, Any

class AnalyzeRequest(BaseModel):
    alert: Dict[str, Any]