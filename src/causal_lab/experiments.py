"""Reproducible offline research cases, deliberately no Fluss performance claims."""
from __future__ import annotations

from .engine import CausalGapError, DecisionEngine
from .ledger import Ledger
from .model import Event
from .scenario import ACCOUNT, DECISION_ID, seed


def run_experiments() -> dict:
    with Ledger() as ledger:
        example = seed(ledger)
        engine = DecisionEngine(ledger)
        late = example["counterfactual"]
        e1 = {
            "name": "E1_late_arrival_knowledge_cutoff",
            "passed": (example["proof"]["verified"] and
                       example["decision"]["result"]["outcome"] == "APPROVE" and
                       late["alternate"]["outcome"] == "BLOCK" and
                       late["newly_known_events"] == ["signal-001"]),
            "original": "APPROVE", "counterfactual": late["alternate"]["outcome"],
        }
        ledger.append(Event(
            "correction-001", ACCOUNT, "risk_correction",
            "2026-10-14T10:30:00Z", "2026-10-14T10:38:00Z",
            {"risk_score": 20, "supersedes": "signal-001"}, source="external_risk_feed",
            parents=("signal-001",),
        ))
        after = engine.counterfactual(DECISION_ID, "2026-10-14T10:39:00Z")
        e2 = {"name": "E2_retrospective_correction", "passed": (
            after["alternate"]["outcome"] == "APPROVE" and
            engine.verify(DECISION_ID)["verified"]),
            "after_correction": after["alternate"]["outcome"],
            "original_proof_still_valid": engine.verify(DECISION_ID)["verified"],
        }
    with Ledger() as ledger:
        ledger.append(Event(
            "orphan-001", "synthetic-orphan", "transaction",
            "2026-10-14T10:00:00Z", "2026-10-14T10:00:00Z",
            {"amount_mxn": 1}, parents=("missing-cause",),
        ))
        engine = DecisionEngine(ledger)
        refused = False
        try:
            engine.decide("reject-me", "synthetic-orphan",
                          "2026-10-14T10:10:00Z", "2026-10-14T10:10:00Z")
        except CausalGapError:
            refused = True
        e3 = {"name": "E3_missing_causal_parent", "passed": refused,
              "fail_closed": refused}
    with Ledger() as ledger:
        seed(ledger)
        ledger.append(Event(
            "implausibly-backdated", ACCOUNT, "risk_signal",
            "2026-10-14T10:31:30Z", "2026-10-14T10:31:30Z",
            {"risk_score": 99}, source="untrusted-replay",
        ))
        # Bad source can claim earlier receipt retroactively: historical proof should fail.
        verification = DecisionEngine(ledger).verify(DECISION_ID)
        e4 = {"name": "E4_backdated_record_detected", "passed": not verification["verified"],
              "proof_verified_after_backdating": verification["verified"]}
    experiments = [e1, e2, e3, e4]
    return {"environment": "offline_SQLite_only", "all_passed": all(e["passed"]
            for e in experiments), "total": len(experiments), "experiments": experiments}
