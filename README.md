# Fluss Causal AI Lab 0.1

**Agent Decision Time Machine:** bitemporal AI evidence, exact replay for
deterministic risk rules, causal-gap detection and safe counterfactuals, with
an optional **real Apache Fluss 1.0 + Flink 1.20** integration.

> Research prototype, not a production banking system. Events are 100% synthetic.

## Quick start — executable offline

Requires Python 3.10+; commands below work on macOS/Linux and Windows PowerShell
when Python is on PATH (omit `make` on Windows).

```bash
python -m pip install -e ".[dev]"
python -m causal_lab.cli demo
python -m causal_lab.cli verify
python -m causal_lab.cli counterfactual
python -m causal_lab.cli experiments
python -m pytest -q
```

The `demo` command writes `.data/causal.sqlite3` and `reports/demo.json`.
The independent `experiments` command writes `reports/experiments.json`
with four pass/fail research hypotheses (no external services required).
Run it only once per DB; reset by deleting `.data/causal.sqlite3` before
seeding again. `verify` and `counterfactual` require the seeded DB.

Expected qualitative outcome:

```text
Original decision: APPROVE (risk 15; only information known at 10:32:15)
Counterfactual: BLOCK (risk 95; event dated 10:30 arrives at 10:35)
Evidence verification: true
Late event: signal-001
External side effects: zero
```

This makes a crucial distinction: **when a signal was valid** versus
**when the decision-maker could know it**. The original decision is not
silently rewritten when a late signal arrives.

## Run the native Apache Fluss bridge

Requires Docker Engine + Compose v2 and enough RAM for Fluss/Flink (~8–16 GB
recommended for experimentation). Start the container stack:

```bash
docker compose -f infra/docker-compose.fluss.yml up -d zookeeper coordinator-server tablet-server jobmanager taskmanager
```

Seed the local database *first* with the quick-start `demo` command, then
publish it into real Fluss from within the Compose network:

```bash
docker compose -f infra/docker-compose.fluss.yml --profile tools run --build --rm bridge
```

`bridge` uses the published `pyfluss==1.0.x` Python client and Fluss-native
APIs: creates `causal_lab.event_log` and `causal_lab.decision_log` as append-only
tables, `causal_lab.account_state` as a PK table, flushes writes and performs
a live PK lookup. The container uses Compose-network DNS for Fluss routing.
There is no local mock of Fluss in the bridge.

To explore the resulting tables through Flink SQL:

```bash
docker compose -f infra/docker-compose.fluss.yml --profile tools run --rm sql-client
```

Then issue each statement separately from `sql/explore_fluss.sql`.
Stop with `docker compose -f infra/docker-compose.fluss.yml down`.
Adding `-v` **destroys persisted Fluss test data**.

**Integration status:** The Fluss bridge and Compose manifest are derived from
the official 1.0 API and quickstart, but a live Docker/Fluss integration run
was **not** possible in the artifact build environment. They are executable
integration code, not a claim of having passed integration tests.

**Important:** Fluss is a live projection here; *historical proof remains
anchored in SQLite*. Bridge re-runs duplicate log entries (no exactly-once
contract). Native per-bucket Fluss read offsets, Iceberg tiering and chaos
experiments are **not implemented in v0.1**.

## Local HTTP inspection API (optional)

```bash
python -m pip install -e ".[api]"
uvicorn causal_lab.api:app --host 127.0.0.1 --port 8000
```

Navigate to `http://127.0.0.1:8000/docs`. The API is read-only and has no
authentication, so do not expose it to a public interface.

## Local microbenchmark (NOT a Fluss performance benchmark)

```bash
python -m causal_lab.cli --db .data/bench.sqlite3 benchmark --accounts 1000
```

This measures only SQLite append and as-of evaluation timings. It cannot be
used to support Fluss latency, throughput, durability or comparison claims.

## Repository layout

```text
src/causal_lab/  immutable event model, SQLite ledger, policy, engine, CLI
src/causal_lab/fluss_bridge.py  native Fluss writer + real PK reader
src/causal_lab/api.py   optional read-only FastAPI endpoints
infra/          Fluss 1.0 / Flink 1.20 Docker Compose and bridge image
sql/            Flink SQL exploration
runs/           reserved for future distributed test scenarios
tests/          offline deterministic regression suite
docs/           research protocol and boundaries
.github/        Python 3.10/3.11/3.12 CI
```

## Capability matrix

| Capability | State | Evidence |
|---|---|---|
| Bitemporal snapshots | Tested locally | `test_bitemporal.py` |
| Proof hash + immutability triggers | Tested locally | regression tests |
| Causal-parent-gap detection | Tested locally | regression tests |
| Counterfactual policy replay | Tested locally | `demo.json`, tests |
| Four independent research experiments | Tested locally | `experiments.json`, tests |
| Real Fluss Python write + lookup | Implemented, cluster run unverified | `fluss_bridge.py` |
| Flink SQL query surface | SQL examples, unverified | `sql/explore_fluss.sql` |
| PostgreSQL CDC / Kafka source | Planned, not implemented | research roadmap |
| Native Fluss offsets / Iceberg tiering | Planned, not implemented | research roadmap |
| Kubernetes chaos / agent tool replay | Planned, not implemented | research roadmap |

## Research discipline

Read [RESEARCH.md](docs/RESEARCH.md) and [ARCHITECTURE.md](docs/ARCHITECTURE.md)
for hypothesis, proof assumptions, reproducibility, threat model and the
precise limits of our claims.

## Upstream references

- https://fluss.apache.org/docs/apis/python/example/
- https://fluss.apache.org/docs/apis/python/installation/
- https://fluss.apache.org/docs/quickstart/page_user_profile/
- https://fluss.apache.org/docs/quickstart/flink/
- https://fluss.apache.org/docs/streaming-lakehouse/tiering-service/
- https://pypi.org/project/pyfluss/1.0.0/

License: Apache-2.0. No endorsement by the Apache Software Foundation.
