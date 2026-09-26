"""Plain data structures shared by every stage of the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SourceRef:
    """Exact location of a figure: a workbook cell or a deck slide/page."""
    file: str
    location: str          # e.g. "Intermediate!H76" or "Slide 19"
    label: str = ""        # quoted label / text next to the figure

    def __str__(self) -> str:
        lab = f' "{self.label}"' if self.label else ""
        return f"{self.file} | {self.location}{lab}"


@dataclass
class Figure:
    value: float
    ref: SourceRef
    note: str = ""


# Severity order used to rank data issues (lower = more material).
SEVERITY_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}


@dataclass
class Issue:
    code: str
    severity: str                  # HIGH / MEDIUM / LOW / INFO
    category: str                  # Mismatch, Formula, Totals, Assumption, Extraction ...
    title: str
    detail: str
    refs: list[str] = field(default_factory=list)
    arithmetic: str = ""
    resolution: str = ""           # which value the calculation uses and why
    priority: int = 50             # tie-breaker within a severity (lower = more material)

    @property
    def rank(self) -> tuple[int, int]:
        return (SEVERITY_RANK.get(self.severity, 9), self.priority)


@dataclass
class ShareClass:
    key: str            # e.g. "CS", "PS3", "OPT", "POOL", "CSW"
    name: str           # display name from the source
    kind: str           # common / preferred / warrant / option / pool
    source_col: str = ""            # Intermediate column letter holding raw shares
    conversion_col: str = ""        # Intermediate column holding as-converted shares

    @property
    def is_outstanding(self) -> bool:
        """Counts toward basic (issued and outstanding) shares."""
        return self.kind in ("common", "preferred")


@dataclass
class HolderRow:
    name: str
    source_row: int
    row_type: str                   # holder / commitment / placeholder / aggregate / pool
    shares: dict[str, float]        # class key -> shares (as-converted, 1:1)
    stakeholder_id: str = ""
    note: str = ""

    def basic(self, classes: list[ShareClass]) -> float:
        return sum(self.shares.get(c.key, 0.0) for c in classes if c.is_outstanding)

    def fully_diluted(self, classes: list[ShareClass]) -> float:
        return sum(self.shares.get(c.key, 0.0) for c in classes)


@dataclass
class CapTable:
    file: str
    company: str
    as_of: str
    classes: list[ShareClass]
    rows: list[HolderRow]
    round_class: str                             # key of the Seed-3 class
    issue_price: Optional[Figure] = None         # explicit Seed-3 price
    source_total_basic: Optional[Figure] = None
    source_total_fd: Optional[Figure] = None
    source_total_fd_alt: Optional[Figure] = None     # e.g. Summary!D33
    source_class_totals: dict[str, list[Figure]] = field(default_factory=dict)
    issue_prices: dict[str, Figure] = field(default_factory=dict)
    # Seed-3 cash components parsed from the source (existing, commitments, open)
    round_cash_existing: Optional[Figure] = None
    round_cash_commitments: Optional[Figure] = None
    round_cash_open: Optional[Figure] = None
    round_cash_total: Optional[Figure] = None
    convertibles: list[Figure] = field(default_factory=list)
    fractional_convention: Optional[str] = None
    extras: dict = field(default_factory=dict)       # parsed details used by validation

    def cls(self, key: str) -> ShareClass:
        return next(c for c in self.classes if c.key == key)

    def rows_of(self, *types: str) -> list[HolderRow]:
        return [r for r in self.rows if r.row_type in types]


@dataclass
class DeckTerms:
    file: str
    pre_money: list[Figure] = field(default_factory=list)
    round_size: list[Figure] = field(default_factory=list)
    committed: list[Figure] = field(default_factory=list)
    open_allocation: list[Figure] = field(default_factory=list)
    share_price: list[Figure] = field(default_factory=list)
    share_counts: list[Figure] = field(default_factory=list)
    lead_investor: list[tuple[str, SourceRef]] = field(default_factory=list)
    image_flags: list[str] = field(default_factory=list)    # slides needing manual review
    slide_count: int = 0


@dataclass
class ResolvedInput:
    name: str
    value: object
    source: str


@dataclass
class Inputs:
    investor: str
    check_size: Optional[float]
    share_price: Optional[float]
    commitments_in_before: Optional[bool]
    uncounted_commitments: Optional[float]        # USD, only when commitments not in Before
    placeholder_mode: str                         # "release" or "keep"
    pre_money: Optional[float]
    resolved: list[ResolvedInput] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.missing)
