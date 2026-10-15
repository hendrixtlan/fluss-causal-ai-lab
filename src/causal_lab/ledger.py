"""Append-only SQLite evidence ledger. This is NOT Fluss's native change log."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Iterable, Any
from .model import Event, canonical, utc_stamp


class DuplicateEventError(ValueError):
    pass


class MissingDecisionError(KeyError):
    pass


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 event_id TEXT NOT NULL UNIQUE,
 account_id TEXT NOT NULL,
 kind TEXT NOT NULL,
 valid_at TEXT NOT NULL,
 observed_at TEXT NOT NULL,
 source TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 parents_json TEXT NOT NULL,
 content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_asof ON events(account_id,observed_at,valid_at);
CREATE TABLE IF NOT EXISTS decisions (
 decision_id TEXT PRIMARY KEY,
 account_id TEXT NOT NULL,
 valid_at TEXT NOT NULL,
 knowledge_at TEXT NOT NULL,
 policy_json TEXT NOT NULL,
 result_json TEXT NOT NULL,
 manifest_json TEXT NOT NULL,
 evidence_hash TEXT NOT NULL,
 decision_hash TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
 BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
 BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_decisions_update BEFORE UPDATE ON decisions
 BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_decisions_delete BEFORE DELETE ON decisions
 BEGIN SELECT RAISE(ABORT, 'decisions are append-only'); END;
"""


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def append(self, event: Event) -> int:
        existing = self.db.execute(
            "SELECT content_hash FROM events WHERE event_id=?", (event.event_id,)
        ).fetchone()
        if existing is not None:
            if existing["content_hash"] == event.content_hash:
                raise DuplicateEventError("duplicate event_id (idempotent duplicate rejected)")
            raise DuplicateEventError("event_id collision with different content")
        cur = self.db.execute(
            """INSERT INTO events(event_id,account_id,kind,valid_at,observed_at,source,
               payload_json,parents_json,content_hash) VALUES(?,?,?,?,?,?,?,?,?)""",
            (event.event_id, event.account_id, event.kind, event.valid_at, event.observed_at,
             event.source, canonical(event.payload), canonical(list(event.parents)),
             event.content_hash),
        )
        self.db.commit()
        return int(cur.lastrowid)

    @staticmethod
    def _event(row: sqlite3.Row) -> Event:
        event = Event(row["event_id"], row["account_id"], row["kind"],
                      row["valid_at"], row["observed_at"],
                      json.loads(row["payload_json"]), row["source"],
                      tuple(json.loads(row["parents_json"])), row["sequence"])
        if event.content_hash != row["content_hash"]:
            raise ValueError(f"corrupt event content: {event.event_id}")
        return event

    def history(self, account_id: str | None = None) -> list[Event]:
        if account_id:
            rows = self.db.execute("SELECT * FROM events WHERE account_id=? ORDER BY observed_at,sequence",
                                   (account_id,)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM events ORDER BY observed_at,sequence").fetchall()
        return [self._event(row) for row in rows]

    def as_of(self, account_id: str, valid_at: str, knowledge_at: str) -> list[Event]:
        valid_at, knowledge_at = utc_stamp(valid_at), utc_stamp(knowledge_at)
        rows = self.db.execute(
            """SELECT * FROM events WHERE account_id=? AND valid_at<=? AND observed_at<=?
               ORDER BY observed_at,sequence""", (account_id,valid_at,knowledge_at)
        ).fetchall()
        return [self._event(row) for row in rows]

    def insert_decision(self, record: dict[str, Any]) -> None:
        self.db.execute("""INSERT INTO decisions(decision_id,account_id,valid_at,knowledge_at,
            policy_json,result_json,manifest_json,evidence_hash,decision_hash)
            VALUES(?,?,?,?,?,?,?,?,?)""", (
            record["decision_id"], record["account_id"], record["valid_at"],
            record["knowledge_at"], canonical(record["policy"]),
            canonical(record["result"]), canonical(record["manifest"]),
            record["evidence_hash"], record["decision_hash"],
        ))
        self.db.commit()

    def decision(self, decision_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM decisions WHERE decision_id=?",
                              (decision_id,)).fetchone()
        if row is None:
            raise MissingDecisionError(decision_id)
        return {
            "decision_id": row["decision_id"], "account_id": row["account_id"],
            "valid_at": row["valid_at"], "knowledge_at": row["knowledge_at"],
            "policy": json.loads(row["policy_json"]),
            "result": json.loads(row["result_json"]),
            "manifest": json.loads(row["manifest_json"]),
            "evidence_hash": row["evidence_hash"],
            "decision_hash": row["decision_hash"],
        }

    def decisions(self) -> list[dict[str, Any]]:
        ids = [row[0] for row in self.db.execute("SELECT decision_id FROM decisions ORDER BY decision_id")]
        return [self.decision(id_) for id_ in ids]
