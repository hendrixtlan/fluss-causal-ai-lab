"""Exact bitemporal reconstruction for deterministic policies; no external side effects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from .ledger import Ledger
from .model import Event, digest, utc_stamp


class CausalGapError(ValueError):
    pass


@dataclass(frozen=True)
class Policy:
    version: str = "risk-v1"
    block_at: int = 70
    review_amount_mxn: int = 100_000

    def as_dict(self) -> dict[str, Any]:
        return {"version": self.version, "block_at": self.block_at,
                "review_amount_mxn": self.review_amount_mxn}


def _materialize(events: list[Event], policy: Policy) -> dict[str, Any]:
    available_ids = {event.event_id for event in events}
    causal_gaps = sorted({f"{event.event_id}->{parent}" for event in events
                          for parent in event.parents if parent not in available_ids})
    corrections = {event.payload["supersedes"] for event in events
                   if event.kind == "risk_correction"}
    active = [event for event in events if event.event_id not in corrections]
    risks = [e for e in active if e.kind in ("profile", "risk_signal", "risk_correction")]
    risk_score = max((e.payload["risk_score"] for e in risks), default=0)
    txs = [e for e in active if e.kind == "transaction"]
    tx = max(txs, key=lambda e: (e.valid_at, e.observed_at, e.sequence or 0)) if txs else None
    amount = tx.payload["amount_mxn"] if tx else 0
    if risk_score >= policy.block_at:
        outcome, rationale = "BLOCK", "risk_threshold"
    elif tx is None:
        outcome, rationale = "REVIEW", "missing_transaction"
    elif amount >= policy.review_amount_mxn:
        outcome, rationale = "REVIEW", "amount_threshold"
    else:
        outcome, rationale = "APPROVE", "within_policy"
    return {"outcome": outcome, "reason": rationale, "risk_score": risk_score,
            "amount_mxn": amount, "transaction_event_id": tx.event_id if tx else None,
            "causal_gaps": causal_gaps, "active_event_ids": [e.event_id for e in active]}


class DecisionEngine:
    def __init__(self, ledger: Ledger, policy: Policy | None = None):
        self.ledger = ledger
        self.policy = policy or Policy()

    def evaluate(self, account_id: str, valid_at: str, knowledge_at: str,
                 strict_causality: bool = True) -> tuple[dict[str, Any], dict[str, Any], str]:
        valid_at, knowledge_at = utc_stamp(valid_at), utc_stamp(knowledge_at)
        events = self.ledger.as_of(account_id, valid_at, knowledge_at)
        result = _materialize(events, self.policy)
        if strict_causality and result["causal_gaps"]:
            raise CausalGapError("unresolved causal dependencies: " +
                                 ", ".join(result["causal_gaps"]))
        per_source = {}
        for ev in events:
            # These are local SQLite sequences, NOT physical Fluss bucket offsets.
            per_source[ev.source] = max(per_source.get(ev.source, 0), ev.sequence or 0)
        manifest = {
            "event_hashes": [{"event_id": ev.event_id, "sha256": ev.content_hash}
                             for ev in events],
            "local_sequence_high_watermarks": dict(sorted(per_source.items())),
            "policy_sha256": digest(self.policy.as_dict()),
        }
        evidence_hash = digest({"manifest": manifest, "valid_at": valid_at,
                                "knowledge_at": knowledge_at, "account_id": account_id})
        return result, manifest, evidence_hash

    def decide(self, decision_id: str, account_id: str, valid_at: str, knowledge_at: str,
               strict_causality: bool = True) -> dict[str, Any]:
        result, manifest, evidence_hash = self.evaluate(
            account_id, valid_at, knowledge_at, strict_causality=strict_causality
        )
        record = {
            "decision_id": decision_id, "account_id": account_id,
            "valid_at": utc_stamp(valid_at), "knowledge_at": utc_stamp(knowledge_at),
            "policy": self.policy.as_dict(), "result": result,
            "manifest": manifest, "evidence_hash": evidence_hash,
        }
        record["decision_hash"] = digest(record)
        self.ledger.insert_decision(record)
        return record

    def verify(self, decision_id: str) -> dict[str, Any]:
        record = self.ledger.decision(decision_id)
        if record["policy"] != self.policy.as_dict():
            return {"decision_id": decision_id, "verified": False,
                    "reason": "policy_version_or_parameters_mismatch"}
        result, manifest, evidence_hash = self.evaluate(
            record["account_id"], record["valid_at"], record["knowledge_at"],
            strict_causality=False,
        )
        expected_hash = digest({k: v for k, v in record.items() if k != "decision_hash"})
        checks = {
            "evidence_hash": evidence_hash == record["evidence_hash"],
            "manifest": manifest == record["manifest"],
            "result": result == record["result"],
            "decision_hash": expected_hash == record["decision_hash"],
            "causal_consistency": not result["causal_gaps"],
        }
        return {"decision_id": decision_id, "verified": all(checks.values()), "checks": checks}

    def counterfactual(self, decision_id: str, knowledge_at: str) -> dict[str, Any]:
        original = self.ledger.decision(decision_id)
        new_knowledge = utc_stamp(knowledge_at)
        if new_knowledge < original["knowledge_at"]:
            raise ValueError("counterfactual knowledge_at must not precede original knowledge")
        alternate, manifest, evidence_hash = self.evaluate(
            original["account_id"], original["valid_at"], new_knowledge
        )
        old_ids = {e["event_id"] for e in original["manifest"]["event_hashes"]}
        new_ids = {e["event_id"] for e in manifest["event_hashes"]}
        return {
            "decision_id": decision_id,
            "valid_at": original["valid_at"],
            "original_knowledge_at": original["knowledge_at"],
            "alternate_knowledge_at": new_knowledge,
            "original": original["result"], "alternate": alternate,
            "outcome_changed": original["result"]["outcome"] != alternate["outcome"],
            "newly_known_events": sorted(new_ids - old_ids),
            "no_longer_visible_events": sorted(old_ids - new_ids),
            "alternate_evidence_hash": evidence_hash,
            "side_effects_executed": 0,
        }
