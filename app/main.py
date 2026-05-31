from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from app.models import AnalyzeRequest
from app.normalize import normalize_alert
from app.analyze import analyze_normalized
from app.alert_management.router import router as alert_management_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # només per desenvolupament
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alert_management_router)

@app.get("/")
def root():
    return {"message": "Backend running"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    alert = req.alert

    normalized = normalize_alert(alert)

    if normalized is None:
        return {
            "status": "error",
            "decision": "SKIP",
            "reason": "Invalid option symbol"
        }

    analysis = analyze_normalized(normalized)

    return {
        "status": "ok",
        **analysis
    }
