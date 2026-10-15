"""CLI. Runs fully offline except the explicit `bridge-fluss` command."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import time
from .engine import DecisionEngine
from .ledger import Ledger
from .model import Event, canonical
from .scenario import ACCOUNT, DECISION_ID, LATER_KNOWLEDGE, seed


def output(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fluss Causal AI Lab: deterministic bitemporal replay")
    parser.add_argument("--db", default=".data/causal.sqlite3", help="SQLite ledger path")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="seed bank scenario, verify and compare counterfactual")
    demo.add_argument("--report", default="reports/demo.json")
    sub.add_parser("verify", help="verify recorded decision evidence")
    replay = sub.add_parser("counterfactual", help="compare with alternate knowledge time")
    replay.add_argument("--knowledge-at", default=LATER_KNOWLEDGE)
    experiments = sub.add_parser("experiments", help="run four isolated offline research hypotheses")
    experiments.add_argument("--report", default="reports/experiments.json")
    bridge = sub.add_parser("bridge-fluss", help="publish ledger to REAL Fluss and verify KV lookup")
    bridge.add_argument("--bootstrap", default=None)
    benchmark = sub.add_parser("benchmark", help="local SQLite-only research microbenchmark")
    benchmark.add_argument("--accounts", type=int, default=100)
    benchmark.add_argument("--report", default="reports/benchmark.json")
    args = parser.parse_args(argv)
    with Ledger(args.db) as ledger:
        if args.command == "demo":
            result = seed(ledger)
            path = Path(args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            output({"report": str(path), "original_outcome": result["decision"]["result"]["outcome"],
                    "alternate_outcome": result["counterfactual"]["alternate"]["outcome"],
                    "verified": result["proof"]["verified"],
                    "late_events": result["counterfactual"]["newly_known_events"]})
        elif args.command == "verify":
            output(DecisionEngine(ledger).verify(DECISION_ID))
        elif args.command == "counterfactual":
            output(DecisionEngine(ledger).counterfactual(DECISION_ID, args.knowledge_at))
        elif args.command == "experiments":
            from .experiments import run_experiments
            research = run_experiments()
            path = Path(args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(research, indent=2) + "\n", encoding="utf-8")
            output(research)
        elif args.command == "bridge-fluss":
            from .fluss_bridge import publish
            output(asyncio.run(publish(ledger, args.bootstrap)))
        elif args.command == "benchmark":
            if args.accounts <= 0 or args.accounts > 100_000:
                raise ValueError("accounts must be between 1 and 100000")
            started = time.perf_counter()
            for i in range(args.accounts):
                ledger.append(Event(
                    event_id=f"bench-profile-{i}", account_id=f"bench-{i}", kind="profile",
                    valid_at="2026-10-14T09:00:00Z", observed_at="2026-10-14T09:00:00Z",
                    payload={"risk_score": i % 100}, source="benchmark",
                ))
            inserted = time.perf_counter()
            engine = DecisionEngine(ledger)
            for i in range(args.accounts):
                engine.evaluate(f"bench-{i}", "2026-10-14T12:00:00Z",
                                "2026-10-14T12:00:00Z")
            completed = time.perf_counter()
            stats = {"backend": "local_sqlite_only", "accounts": args.accounts,
                     "append_seconds": round(inserted-started, 6),
                     "evaluate_seconds": round(completed-inserted, 6),
                     "total_seconds": round(completed-started, 6)}
            path = Path(args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(stats, indent=2)+"\n", encoding="utf-8")
            output(stats)


if __name__ == "__main__":
    main()
