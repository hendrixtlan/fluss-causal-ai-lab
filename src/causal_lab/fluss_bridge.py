"""Optional integration with REAL Apache Fluss 1.0 via native PyFluss client.

It publishes a mirror of the durable local evidence ledger. The authoritative
as-of reconstruction in v0.1 remains SQLite. This bridge does NOT provide
atomic cross-store writes, exactly-once guarantees, or native Fluss offsets.
"""
from __future__ import annotations

import os
from .engine import DecisionEngine
from .ledger import Ledger
from .model import canonical


async def publish(ledger: Ledger, bootstrap: str | None = None) -> dict:
    try:
        import fluss
        import pyarrow as pa
    except ImportError as exc:
        raise RuntimeError("pip install '.[fluss]' to enable the native Fluss bridge") from exc
    address = bootstrap or os.getenv("FLUSS_BOOTSTRAP", "coordinator-server:9123")
    conn = await fluss.FlussConnection.create(fluss.Config({"bootstrap.servers": address}))
    try:
        admin = conn.get_admin()
        await admin.create_database("causal_lab", ignore_if_exists=True)
        specs = {
            "event_log": fluss.Schema(pa.schema([
                pa.field("event_id", pa.string()), pa.field("account_id", pa.string()),
                pa.field("kind", pa.string()), pa.field("valid_at", pa.string()),
                pa.field("observed_at", pa.string()), pa.field("source", pa.string()),
                pa.field("payload_json", pa.string()), pa.field("sha256", pa.string()),
            ])),
            "decision_log": fluss.Schema(pa.schema([
                pa.field("decision_id", pa.string()), pa.field("account_id", pa.string()),
                pa.field("valid_at", pa.string()), pa.field("knowledge_at", pa.string()),
                pa.field("outcome", pa.string()), pa.field("evidence_sha256", pa.string()),
                pa.field("decision_sha256", pa.string()),
            ])),
            "account_state": fluss.Schema(pa.schema([
                pa.field("account_id", pa.string()), pa.field("risk_score", pa.int32()),
                pa.field("knowledge_at", pa.string()), pa.field("outcome", pa.string()),
            ]), primary_keys=["account_id"]),
        }
        for name, schema in specs.items():
            await admin.create_table(
                fluss.TablePath("causal_lab", name),
                fluss.TableDescriptor(schema, bucket_count=3), ignore_if_exists=True,
            )
        events = ledger.history()
        event_table = await conn.get_table(fluss.TablePath("causal_lab", "event_log"))
        event_writer = event_table.new_append().create_writer()
        for event in events:
            event_writer.append({
                "event_id": event.event_id, "account_id": event.account_id,
                "kind": event.kind, "valid_at": event.valid_at,
                "observed_at": event.observed_at, "source": event.source,
                "payload_json": canonical(event.payload), "sha256": event.content_hash,
            })
        await event_writer.flush()

        decisions = ledger.decisions()
        decision_table = await conn.get_table(fluss.TablePath("causal_lab", "decision_log"))
        decision_writer = decision_table.new_append().create_writer()
        for decision in decisions:
            decision_writer.append({
                "decision_id": decision["decision_id"], "account_id": decision["account_id"],
                "valid_at": decision["valid_at"], "knowledge_at": decision["knowledge_at"],
                "outcome": decision["result"]["outcome"],
                "evidence_sha256": decision["evidence_hash"],
                "decision_sha256": decision["decision_hash"],
            })
        await decision_writer.flush()

        state_table = await conn.get_table(fluss.TablePath("causal_lab", "account_state"))
        state_writer = state_table.new_upsert().create_writer()
        accounts = sorted({e.account_id for e in events})
        for account in accounts:
            account_events = [e for e in events if e.account_id == account]
            cutoff = max(e.observed_at for e in account_events)
            state, _, _ = DecisionEngine(ledger).evaluate(account, cutoff, cutoff)
            state_writer.upsert({
                "account_id": account, "risk_score": state["risk_score"],
                "knowledge_at": cutoff, "outcome": state["outcome"],
            })
        await state_writer.flush()

        verified = {}
        lookuper = state_table.new_lookup().create_lookuper()
        for account in accounts:
            result = await lookuper.lookup({"account_id": account})
            if result is None:
                raise RuntimeError(f"Fluss KV lookup failed for {account}")
            verified[account] = {"risk_score": result["risk_score"],
                                 "outcome": result["outcome"]}
        return {"backend": "real_apache_fluss", "bootstrap": address,
                "events_appended": len(events), "decisions_appended": len(decisions),
                "kv_records_upserted": len(accounts), "kv_lookup_verified": verified,
                "delivery_semantics": "at-least-once demonstration; re-running appends duplicate logs"}
    finally:
        await conn.close()
