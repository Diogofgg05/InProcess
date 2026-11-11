"""Typed mapping preserves the existing public dictionary contract."""
from typing import TypedDict,NotRequired


class ProcessRecord(TypedDict):
    pid: int
    name: str
    user: str
    status: str
    cpu: float | None
    memory: int
    created: float
    elapsed: float
    disk: float | None
    network: float | None
    gpu: float | None
    kind: NotRequired[str]
    status_sampled_at: NotRequired[float]
    status_age_s: NotRequired[float]
    kind_sampled_at: NotRequired[float | None]
    kind_age_s: NotRequired[float | None]
