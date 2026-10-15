"""Entirely synthetic bank transfer dataset; uses fixed UTC timestamps."""
from .ledger import Ledger
from .model import Event
from .engine import DecisionEngine

ACCOUNT = "acct-synthetic-001"
DECISION_ID = "decision-synthetic-001"
VALID_AT = "2026-10-14T10:32:15Z"
ORIGINAL_KNOWLEDGE = "2026-10-14T10:32:15Z"
LATER_KNOWLEDGE = "2026-10-14T10:36:00Z"


def seed(ledger: Ledger) -> dict:
    """Seed only an empty ledger, then decide after all events are recorded.

    Insertion order is NOT knowledge order; observed_at determines visibility.
    """
    if ledger.history():
        raise ValueError("seed requires empty ledger")
    ledger.append(Event(
        event_id="profile-001", account_id=ACCOUNT, kind="profile",
        valid_at="2026-10-14T10:00:00Z", observed_at="2026-10-14T10:00:02Z",
        payload={"risk_score": 15}, source="customer_profile",
    ))
    ledger.append(Event(
        event_id="tx-001", account_id=ACCOUNT, kind="transaction",
        valid_at="2026-10-14T10:31:00Z", observed_at="2026-10-14T10:31:01Z",
        payload={"amount_mxn": 85000}, source="payments_cdc",
        parents=("profile-001",),
    ))
    ledger.append(Event(
        event_id="signal-001", account_id=ACCOUNT, kind="risk_signal",
        valid_at="2026-10-14T10:30:00Z", observed_at="2026-10-14T10:35:00Z",
        payload={"risk_score": 95}, source="external_risk_feed",
    ))
    engine = DecisionEngine(ledger)
    decision = engine.decide(DECISION_ID, ACCOUNT, VALID_AT, ORIGINAL_KNOWLEDGE)
    proof = engine.verify(DECISION_ID)
    comparison = engine.counterfactual(DECISION_ID, LATER_KNOWLEDGE)
    return {"decision": decision, "proof": proof, "counterfactual": comparison}
