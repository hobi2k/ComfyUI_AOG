"""Shared node result types used by the CLI validation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeResult:
    """Store a node payload together with non-fatal warnings."""

    name: str
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


class BaseNode:
    """Define the common interface every validation node should implement."""

    name = "base"

    def run(self, **_: Any) -> NodeResult:
        """Execute the node and return a structured payload."""
        raise NotImplementedError
