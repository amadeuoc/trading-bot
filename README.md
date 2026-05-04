# Trading Bot – Bullflow Alerts Analyzer

## Overview

This project is a real-time trading alert system that:

- Listens to alerts from Firebase (Bullflow-style)
- Displays them in a web interface
- Sends each alert to a Python backend
- Validates the alert
- (In progress) generates a trading order candidate

---

## Architecture

Firestore → Frontend → Backend → Decision → UI

Flow:

1. User logs in via Firebase
2. Frontend listens to _flow_alerts
3. Alerts are received in real time
4. Each alert is sent to /analyze
5. Backend normalizes and analyzes the alert
6. Backend returns decision + order
7. Frontend displays result

---

## Project Structure

trading-bot/
  app/                Backend (FastAPI)
    main.py
    models.py
    normalize.py
    analyze.py

  frontend/           Frontend (HTML + JS)
    index.html

  requirements.txt
  README.md

---

## Backend

Tech:
- FastAPI
- Pydantic
- Uvicorn

Endpoint:

POST /analyze

Input:

{
  "alert": { ... }
}

Output:

{
  "decision": "VALID | REJECT | SKIP",
  "reason": "...",
  "checks": { ... },
  "order": {
    "entry": null,
    "stopLoss": null,
    "takeProfit": null
  }
}

---

## Normalization

File: app/normalize.py

Transforms raw alert into structured data:
- underlying
- option (type, strike, expiration)
- trade (price, premium)
- context (tags, execution)
- raw

---

## Analysis Logic

File: app/analyze.py

Current rule:

if premium >= 10000:
    decision = "VALID"
else:
    decision = "REJECT"

This will evolve into a full trading strategy engine.

---

## Frontend

Tech:
- Vanilla JavaScript
- Firebase Auth
- Firestore

Features:
- Real-time alerts
- Sources: personal, system, shared
- Filtering
- Sorting by timestamp
- Alert cards
- Raw JSON view
- Backend validation result
- Sound on new alerts

---

## Backend Integration

Frontend calls:

http://localhost:8000/analyze

---

## Current Status

- Alerts working
- Backend validation working
- Git configured
- Codex CLI integrated
- Order placeholders added

---

## Next Steps

- Compute real order values:
  entry, stopLoss, takeProfit

- Improve analysis logic:
  volume, spread, context

- Risk management

- IBKR integration

---

## Development

Run backend:

uvicorn app.main:app --reload

Run frontend:

cd frontend
python3 -m http.server 5500

---

## Codex Usage

Run:

codex

Example prompts:
- Explain this project
- Improve analyze logic
- Add order calculation

---

## Goal

Build a real-time trading decision engine that:
- understands alerts
- filters noise
- generates actionable trades
