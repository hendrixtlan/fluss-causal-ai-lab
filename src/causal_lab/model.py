"""Immutable events, UTC normalization and deterministic content digests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


ALLOWED_KINDS = frozenset({"profile", "risk_signal", "risk_correction", "transaction"})


def utc_stamp(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        raise ValueError("timestamps must have UTC offset or Z")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    event_id: str
    account_id: str
    kind: str
    valid_at: str
    observed_at: str
    payload: dict[str, Any]
    source: str = "synthetic"
    parents: tuple[str, ...] = field(default_factory=tuple)
    sequence: int | None = None

    def __post_init__(self):
        if not self.event_id or not self.account_id or not self.source:
            raise ValueError("event_id, account_id and source must be non-empty")
        if self.kind not in ALLOWED_KINDS:
            raise ValueError(f"unknown event kind: {self.kind}")
        object.__setattr__(self, "valid_at", utc_stamp(self.valid_at))
        object.__setattr__(self, "observed_at", utc_stamp(self.observed_at))
        object.__setattr__(self, "parents", tuple(self.parents))
        if self.event_id in self.parents or len(set(self.parents)) != len(self.parents):
            raise ValueError("invalid causal parents")
        if self.kind in {"profile", "risk_signal", "risk_correction"}:
            score = self.payload.get("risk_score")
            if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
                raise ValueError("risk_score must be integer 0..100")
        if self.kind == "transaction":
            amount = self.payload.get("amount_mxn")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise ValueError("amount_mxn must be positive integer")
        if self.kind == "risk_correction" and not self.payload.get("supersedes"):
            raise ValueError("risk_correction needs supersedes event id")

    def body(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "account_id": self.account_id, "kind": self.kind,
            "valid_at": self.valid_at, "observed_at": self.observed_at,
            "payload": self.payload, "source": self.source, "parents": list(self.parents),
        }

    @property
    def content_hash(self) -> str:
        return digest(self.body())
