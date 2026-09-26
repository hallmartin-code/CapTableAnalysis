"""Ownership calculation.  Pure functions: no I/O, no rounding of share counts.

Definitions
- Basic: issued and outstanding common + preferred (1:1 as converted).  Excludes
  options/RSUs, warrants and the unissued pool.
- Fully diluted: basic + warrants + options/RSUs + unissued pool.
- Before: the source pro forma exactly as reported.
- After: Before + (commitments not in Before) + (release of an unsold plug row,
  if chosen) + new-investor shares.  Every adjustment is a separate column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import CapTable, Inputs

NEW_INVESTOR = "new_investor"
UNCOUNTED = "uncounted_commitments"


class CalculationBlocked(Exception):
    def __init__(self, missing: list[str]):
        super().__init__("; ".join(missing))
        self.missing = missing


@dataclass
class OutRow:
    name: str
    row_type: str
    source_ref: str
    before: dict[str, float]
    adj_commit: float = 0.0          # Seed-3 shares, commitments not in Before
    adj_placeholder: float = 0.0     # Seed-3 shares, release of unsold plug row
    new_shares: float = 0.0          # Seed-3 shares, this investor
    before_basic: float = 0.0
    before_fd: float = 0.0
    after_basic: float = 0.0
    after_fd: float = 0.0
    pct_before_basic: float = 0.0
    pct_before_fd: float = 0.0
    pct_after_basic: float = 0.0
    pct_after_fd: float = 0.0

    @property
    def delta_basic(self) -> float:
        return self.pct_after_basic - self.pct_before_basic

    @property
    def delta_fd(self) -> float:
        return self.pct_after_fd - self.pct_before_fd


@dataclass
class ClassRow:
    key: str
    name: str
    kind: str
    before: float
    after: float
    pct_before_basic: Optional[float]
    pct_after_basic: Optional[float]
    pct_before_fd: float
    pct_after_fd: float


@dataclass
class Result:
    rows: list[OutRow]
    classes: list[ClassRow]
    new_shares: float
    investor_row: OutRow
    totals: dict[str, float]
    valuation: dict[str, float]
    post_bridge: list[tuple[str, float]]
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def calculate(cap: CapTable, inp: Inputs, derived: Optional[dict] = None) -> Result:
    if inp.missing:
        raise CalculationBlocked(inp.missing)
    problems = []
    if inp.check_size is None or inp.check_size <= 0:
        problems.append("Check size must be a positive dollar amount.")
    if inp.share_price is None or inp.share_price <= 0:
        problems.append("Share price must be a positive dollar amount.")
    if inp.commitments_in_before is False and (inp.uncounted_commitments is None or inp.uncounted_commitments < 0):
        problems.append("Commitments are not in Before, but the uncounted commitment amount is not established.")
    if inp.placeholder_mode not in ("release", "keep"):
        problems.append("Open-allocation placeholder treatment must be 'release' or 'keep'.")
    if problems:
        raise CalculationBlocked(problems)

    rc = cap.round_class
    classes = cap.classes
    price = inp.share_price
    new_shares = inp.check_size / price                      # exact; never rounded
    commit_shares = (inp.uncounted_commitments / price) if inp.commitments_in_before is False else 0.0

    rows: list[OutRow] = []
    for r in cap.rows:
        o = OutRow(r.name, r.row_type, f"{cap.extras.get('detail_sheet', '')} row {r.source_row}", dict(r.shares))
        if r.row_type == "placeholder" and inp.placeholder_mode == "release":
            o.adj_placeholder = -r.shares.get(rc, 0.0)
        rows.append(o)
    if inp.commitments_in_before is False:
        rows.append(OutRow("Seed-3 commitments not in source cap table (aggregate; holders not named)",
                           UNCOUNTED, "User input", {}, adj_commit=commit_shares))
    inv = OutRow(inp.investor, NEW_INVESTOR, "User input", {}, new_shares=new_shares)
    rows.append(inv)

    def basic(d):
        return sum(d.get(c.key, 0.0) for c in classes if c.is_outstanding)

    def fd(d):
        return sum(d.get(c.key, 0.0) for c in classes)

    for o in rows:
        o.before_basic, o.before_fd = basic(o.before), fd(o.before)
        adj = o.adj_commit + o.adj_placeholder + o.new_shares      # all Seed-3 preferred (outstanding)
        o.after_basic, o.after_fd = o.before_basic + adj, o.before_fd + adj

    tb = sum(o.before_basic for o in rows)
    tf = sum(o.before_fd for o in rows)
    ta = sum(o.after_basic for o in rows)
    taf = sum(o.after_fd for o in rows)
    for o in rows:
        o.pct_before_basic, o.pct_before_fd = o.before_basic / tb, o.before_fd / tf
        o.pct_after_basic, o.pct_after_fd = o.after_basic / ta, o.after_fd / taf

    class_rows = []
    for c in classes:
        b = sum(o.before.get(c.key, 0.0) for o in rows)
        a = b + (sum(o.adj_commit + o.adj_placeholder + o.new_shares for o in rows) if c.key == rc else 0.0)
        class_rows.append(ClassRow(c.key, c.name, c.kind, b, a,
                                   b / tb if c.is_outstanding else None, a / ta if c.is_outstanding else None,
                                   b / tf, a / taf))

    # Valuation ------------------------------------------------------------------------
    d = derived or {}
    round_before = sum(o.before.get(rc, 0.0) for o in rows)
    pre_basic = tb - round_before
    pre_fd = tf - round_before
    existing_cash = cap.round_cash_existing.value if cap.round_cash_existing else 0.0
    commit_cash = cap.round_cash_commitments.value if cap.round_cash_commitments else 0.0
    open_cash = cap.round_cash_open.value if cap.round_cash_open else 0.0
    kept_open = open_cash if inp.placeholder_mode == "keep" else 0.0
    uncounted = inp.uncounted_commitments if inp.commitments_in_before is False else 0.0
    proceeds = existing_cash + commit_cash + kept_open + uncounted + inp.check_size
    pre = inp.pre_money if inp.pre_money is not None else price * pre_basic
    val = {
        "pre_money": pre,
        "proceeds": proceeds,
        "proceeds_existing": existing_cash,
        "proceeds_commitments_in_before": commit_cash,
        "proceeds_open_kept": kept_open,
        "proceeds_uncounted": uncounted,
        "proceeds_new": inp.check_size,
        "post_money": pre + proceeds,
        "pre_round_basic_shares": pre_basic,
        "pre_round_fd_shares": pre_fd,
        "implied_pre_basic": price * pre_basic,
        "implied_pre_fd": price * pre_fd,
        "implied_post_basic": price * ta,
        "implied_post_fd": price * taf,
    }
    # Bridge: stated-basis post-money -> price x after outstanding shares.  Components sum exactly.
    named = sum(o.before.get(rc, 0.0) for o in rows if o.row_type in ("holder", "aggregate"))
    commit_rows = sum(o.before.get(rc, 0.0) for o in rows if o.row_type == "commitment")
    ph = sum(o.before.get(rc, 0.0) + o.adj_placeholder for o in rows if o.row_type == "placeholder")
    bridge = [
        ("Pre-money: price x pre-round outstanding shares less stated pre-money", price * pre_basic - pre),
        ("Issued Seed-3: shares x price less recorded cash", named * price - existing_cash),
        ("Commitment rows in Before: shares x price less recorded cash", commit_rows * price - commit_cash),
        ("Unsold plug row kept in After: shares x price less its cash", ph * price - kept_open),
    ]
    diff = val["implied_post_basic"] - val["post_money"]
    bridge.append(("Unexplained remainder", diff - sum(v for _, v in bridge)))
    val["post_diff_basic"] = diff

    res = Result(rows, class_rows, new_shares, inv,
                 {"before_basic": tb, "before_fd": tf, "after_basic": ta, "after_fd": taf}, val, bridge)

    # Checks -----------------------------------------------------------------------------
    def chk(name, ok, detail):
        res.checks.append((name, bool(ok), detail))

    if cap.source_total_basic:
        chk("Before outstanding ties to source", abs(tb - cap.source_total_basic.value) <= 0.01,
            f"{tb:,.2f} vs {cap.source_total_basic.value:,.2f} ({cap.source_total_basic.ref.location})")
    if cap.source_total_fd:
        chk("Before fully diluted ties to source", abs(tf - cap.source_total_fd.value) <= 0.01,
            f"{tf:,.2f} vs {cap.source_total_fd.value:,.2f} ({cap.source_total_fd.ref.location})")
    cls_ok = all(abs(cr.before - f.value) <= 0.01 for cr in class_rows
                 for f in cap.source_class_totals.get(cr.key, []))
    chk("Class totals tie to source", cls_ok, "every class vs Intermediate and Summary totals")
    chk("After ownership sums to 100%", abs(sum(o.pct_after_basic for o in rows) - 1) < 1e-9
        and abs(sum(o.pct_after_fd for o in rows) - 1) < 1e-9, "basic and fully diluted")
    chk("After class totals equal After row totals", abs(sum(c.after for c in class_rows) - taf) < 1e-6,
        f"{sum(c.after for c in class_rows):,.2f} vs {taf:,.2f}")
    neg = [o.name for o in rows if o.after_fd < -1e-9 or o.after_basic < -1e-9]
    chk("No negative share counts", not neg, ", ".join(neg) or "none")
    chk("Fractional new-investor shares", abs(new_shares - round(new_shares)) < 1e-9,
        f"{new_shares:,.6f} shares (no fractional-share convention stated; confirm issued count)")
    if open_cash and inp.check_size > open_cash + 1:
        res.warnings.append(f"Check size exceeds the cap table's open allocation ({open_cash:,.0f}).")
    return res
