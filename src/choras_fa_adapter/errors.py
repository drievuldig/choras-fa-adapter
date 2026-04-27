from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AdapterError(Exception):
    stage: str
    message: str

    def __str__(self) -> str:
        return self.message


def stage_error(
    stage: str, message: str, *, cause: Exception | None = None
) -> AdapterError:
    detail = message
    if cause is not None:
        detail = f"{message}: {cause}"
    return AdapterError(stage=stage, message=detail)
