from dataclasses import dataclass,field
from collections.abc import Sequence


@dataclass(frozen=True)
class Curve:
    name: str
    x: Sequence[float]
    y: Sequence[float]
    color: str = '#2176c1'


@dataclass(frozen=True)
class Figure:
    title: str
    x_label: str
    y_label: str
    curves: Sequence[Curve]
    equal_scale: bool = False


@dataclass(frozen=True)
class Table:
    title: str
    headers: Sequence[str]
    rows: Sequence[Sequence[object]]


@dataclass
class ScientificReport:
    title: str
    kind: str
    provenance: str
    problem: str
    parameters: list[tuple[str,object,str]] = field(default_factory=list)
    equations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    figures: list[Figure] = field(default_factory=list)
    interpretation: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    reproduction: list[str] = field(default_factory=list)
    technical_notes: str = ''
    metadata: dict = field(default_factory=dict)
