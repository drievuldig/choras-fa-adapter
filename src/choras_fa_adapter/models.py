from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ProgressPercentage = int


@dataclass(frozen=True)
class BoundaryMaterial:
    name: str
    absorption: list[float]


@dataclass(frozen=True)
class MeshInlinePayload:
    mesh_id: str
    name: str
    ply_b64: str
    decoded_size_bytes: int


@dataclass(frozen=True)
class FaRunStatus:
    status: str
    progress: float | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    correlation_id: str | None


@dataclass(frozen=True)
class AdapterOutcome:
    run_id: str
    status: str
    correlation_id: str | None
