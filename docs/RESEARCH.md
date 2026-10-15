# Research design — causal proof versus simple replay

## Hypothesis

An AI decision can be reproducibly audited if every consulted fact, policy, read
cutoff, causal dependency and tool response is recorded at the time of use. A
streaming log and a current-state KV lookup alone cannot prove an agent's past
knowledge. A bitemporal evidence ledger can make this testable.

## What the prototype measures

**E1 — Late arrival.** An external risk alert with valid time 10:30 is ingested
at 10:35, after the 10:32 decision. The original evaluation must exclude it;
a counterfactual with later knowledge must include it.

**E2 — Corrections.** A later correction can supersede a signal without rewriting
earlier evidence. Original decision proof must remain stable.

**E3 — Causal dependency.** A consumed event refers to a missing parent. Strict
mode fails closed; non-strict mode allows a diagnostic record but refuses proof.

**E4 — Backdated knowledge.** An untrusted producer inserts an event with a
retroactively claimed receipt time. Historical evidence verification must fail
when recalculated rather than silently certify the old decision.

**Additional invariant — Append-only audit.** SQL UPDATE and DELETE to the evidence tables are
blocked by triggers. This protects accidental writes, not a compromised DBA or
host. SHA-256 is an integrity checksum, not a cryptographic signature.

**E5 — Live data.** Fluss 1.0 receives append-only event/decision logs and a
PK account-state snapshot. A Fluss point lookup confirms the materialized
current record. This is a demonstration of native integration, NOT proof of
atomic cross-store commits or physical bucket-offset capture.

## Exactness conditions

Claims of historical completeness require all read paths to be instrumented.
In particular, original LLM inputs/outputs, tool versions, retrieval results,
seed/temperature, policy/version, and external side effects need recorded
provenance. Model outputs may remain nondeterministic even with pinned seeds.

## Reproducibility

Synthetic fixed UTC times and integer amounts eliminate wall-clock dependence
and floating-point money. The local runner is offline and deterministic.
Fluss integration requires Docker images, a running server, and the native
client; it was not executed in the build environment.

## Future experiments (not implemented)

1. Capture true Fluss bucket/offset evidence at read time; test partition
   ordering and causal watermark consistency across buckets.
2. Replace SQLite as sole historical authority with Fluss log consumption,
   persisted checkpoint tokens, bounded lag, and idempotent sinks.
3. Add actual PostgreSQL CDC, Kafka and Flink SQL pipelines.
4. Implement Apache Iceberg tiering with snapshot retention and replay
   across hot/cold boundaries. The current Compose deliberately omits Iceberg.
5. Add Testcontainers, Jepsen-style failpoints, network partitions and
   crash/restart assertions with proof invariants.
6. Instrument LangGraph tool calls and supply isolated, fake-only side-effect
   adapters with deterministic and nondeterministic evaluation suites.
7. Compare with Kafka + Redis + Iceberg under identical hardware,
   durability levels, read consistency and workloads.

## Threat model and limitations

- Event timestamps are trusted in v0.1; no external attestation.
- An administrator can replace the SQLite file; no tamper-evident remote
  anchoring, signed logs, WORM storage or chain-of-custody guarantees.
- Fluss mirror has at-least-once *demo-level* delivery. Re-running the bridge
  appends duplicate log rows; do not infer exactly-once semantics.
- Local row sequence IDs are NOT Fluss bucket offsets or vector clocks.
- The latest account_state is an illustrative KV projection, not a snapshot
  of the agent's original read.
- No personal data, production banking integrations, or real payment actions.
- API is read-only and binds locally; it is not authenticated.
