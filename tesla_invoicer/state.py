"""Persist OAuth tokens and processed invoice IDs."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class State:
    refresh_token: str | None = None
    access_token: str | None = None
    expires_at: int = 0
    processed_invoices: set[str] = field(default_factory=set)

    def is_token_valid(self, buffer_seconds: int = 300) -> bool:
        return bool(self.access_token) and self.expires_at > int(time.time()) + buffer_seconds

    def mark_processed(self, content_id: str) -> None:
        self.processed_invoices.add(content_id)

    def is_processed(self, content_id: str) -> bool:
        return content_id in self.processed_invoices

    def to_dict(self) -> dict[str, Any]:
        return {
            "refresh_token": self.refresh_token,
            "access_token": self.access_token,
            "expires_at": self.expires_at,
            "processed_invoices": sorted(self.processed_invoices),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> State:
        processed = data.get("processed_invoices") or []
        return cls(
            refresh_token=data.get("refresh_token"),
            access_token=data.get("access_token"),
            expires_at=int(data.get("expires_at") or 0),
            processed_invoices=set(processed),
        )


def load_state(path: Path) -> State:
    if not path.exists():
        return State()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return State.from_dict(data)


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, indent=2)
        handle.write("\n")
    os.chmod(tmp_path, 0o600)
    tmp_path.replace(path)


def clear_processed_invoices(path: Path) -> int:
    """Clear processed invoice IDs so the next sync re-downloads everything."""
    state = load_state(path)
    count = len(state.processed_invoices)
    state.processed_invoices.clear()
    save_state(path, state)
    return count
