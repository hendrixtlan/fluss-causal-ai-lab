"""Optional read-only local development API; no authentication or public exposure."""
from __future__ import annotations

import os
from fastapi import FastAPI, HTTPException
from .ledger import Ledger, MissingDecisionError
from .engine import DecisionEngine

app = FastAPI(title="Fluss Causal AI Lab", version="0.1.0")


def store():
    return Ledger(os.getenv("CAUSAL_DB", ".data/causal.sqlite3"))


@app.get("/health")
def health():
    return {"status": "ok", "mode": "local-ledger"}


@app.get("/decisions/{decision_id}")
def decision(decision_id: str):
    with store() as ledger:
        try:
            return ledger.decision(decision_id)
        except MissingDecisionError as exc:
            raise HTTPException(status_code=404, detail="decision not found") from exc


@app.get("/decisions/{decision_id}/verify")
def verify(decision_id: str):
    with store() as ledger:
        try:
            return DecisionEngine(ledger).verify(decision_id)
        except MissingDecisionError as exc:
            raise HTTPException(status_code=404, detail="decision not found") from exc


@app.get("/decisions/{decision_id}/counterfactual")
def compare(decision_id: str, knowledge_at: str):
    with store() as ledger:
        try:
            return DecisionEngine(ledger).counterfactual(decision_id, knowledge_at)
        except MissingDecisionError as exc:
            raise HTTPException(status_code=404, detail="decision not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
