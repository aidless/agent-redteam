"""MemoryStore ABC + MemoryEntry dataclass (survey §6)."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class MemoryEntry:
    """A single memory entry.

    `content`  — the body of the entry (string, dict, or list)
    `role`     — speaker / source label (e.g. "planner", "verifier")
    `round`    — communication round when the entry was written
    `tags`     — free-form labels (e.g. "attack", "defense")
    `metadata` — arbitrary side-channel info (cost, token count, ...)
    """
    content: Any
    role: str = "user"
    round: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class MemoryStore(abc.ABC):
    """Abstract memory store (survey §6)."""

    @abc.abstractmethod
    def add(self, entry: MemoryEntry) -> None:
        """Append an entry. Implementations may compress or filter."""

    @abc.abstractmethod
    def retrieve(self, query: str, k: int = 5) -> List[MemoryEntry]:
        """Return the `k` most relevant entries for `query`."""

    @abc.abstractmethod
    def reset(self) -> None:
        """Clear all stored state."""

    def __len__(self) -> int:
        return 0

    def all_entries(self) -> List[MemoryEntry]:
        """Return every stored entry (insertion order). Default impl
        requires subclasses to expose `_entries`; otherwise override."""
        return list(getattr(self, "_entries", []))

    def to_dict(self) -> dict:
        """Serialise for dashboards / persistence."""
        return {
            "type": type(self).__name__,
            "size": len(self),
            "entries": [e.to_dict() for e in self.all_entries()],
        }