import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from captable_app.models import (CapTable, DeckTerms, Figure, HolderRow, Inputs, ShareClass,  # noqa: E402
                                 SourceRef)
from captable_app.validate import Review  # noqa: E402

CAP_XLSX = os.path.join(ROOT, "inputs", "GridMatrix Pro Forma Cap Table April 2025.xlsx")
DECK_PPTX = os.path.join(ROOT, "inputs", "GridMatrix Deck.pptx")
real_sources = pytest.mark.skipif(not (os.path.exists(CAP_XLSX) and os.path.exists(DECK_PPTX)),
                                  reason="supplied source files not present")


def ref(loc, label=""):
    return SourceRef("test.xlsx", loc, label)


def make_cap(**overrides) -> CapTable:
    """Small pro forma: 10,000 outstanding, 12,000 fully diluted, Seed-3 at $1.00.

    Seed-3 rows: an issued holder (1,000), a commitment row already in Before (500) and an
    unsold 'Remaining Round Planned' plug (500).
    """
    classes = [
        ShareClass("CS", "Common (CS) Stock", "common", "C"),
        ShareClass("PS1", "Series Seed-1 Preferred (PS1)", "preferred", "D", "E"),
        ShareClass("PS3", "Series Seed-3 Preferred (PS3)", "preferred", "H", "I"),
        ShareClass("OPT", "Options & RSUs outstanding", "option", "L"),
        ShareClass("POOL", "Unissued option pool", "pool", "L"),
    ]
    rows = [
        HolderRow("Founder", 6, "holder", {"CS": 6000.0}, "id1"),
        HolderRow("Fund A", 7, "holder", {"PS1": 2000.0}, "id2"),
        HolderRow("Angel B", 8, "holder", {"PS3": 1000.0}, "id3"),
        HolderRow("Angel Group C", 9, "commitment", {"PS3": 500.0}),
        HolderRow("Remaining Round Planned", 10, "placeholder", {"PS3": 500.0}),
        HolderRow("Other common holders", 11, "aggregate", {"OPT": 1000.0}),
        HolderRow("Shares available for issuance under the plan", 12, "pool", {"POOL": 1000.0}),
    ]
    cap = CapTable(
        file="test.xlsx", company="TestCo", as_of="1/1/2025", classes=classes, rows=rows, round_class="PS3",
        issue_price=Figure(1.0, ref("Intermediate!H76", "Share Class Original Issue Price")),
        source_total_basic=Figure(10000.0, ref("Intermediate!N74")),
        source_total_fd=Figure(12000.0, ref("Intermediate!O72")),
        source_total_fd_alt=Figure(12000.0, ref("Summary!D33")),
        source_class_totals={"CS": [Figure(6000.0, ref("Intermediate!C72"))],
                             "PS1": [Figure(2000.0, ref("Intermediate!E72"))],
                             "PS3": [Figure(2000.0, ref("Intermediate!I72"))],
                             "OPT": [Figure(1000.0, ref("Summary!D30"))],
                             "POOL": [Figure(1000.0, ref("Summary!D31"))]},
        round_cash_existing=Figure(1000.0, ref("Summary!F13", "issued")),
        round_cash_commitments=Figure(500.0, ref("Summary!F13", "commitments")),
        round_cash_open=Figure(500.0, ref("Summary!F13", "open")),
        round_cash_total=Figure(2000.0, ref("Summary!F13", "Cash Raised (USD)")),
    )
    cap.extras["detail_sheet"] = "Intermediate"
    for k, v in overrides.items():
        setattr(cap, k, v)
    return cap


def make_inputs(**kw) -> Inputs:
    base = dict(investor="New investor", check_size=500.0, share_price=1.0, commitments_in_before=True,
                uncounted_commitments=None, placeholder_mode="release", pre_money=8000.0)
    base.update(kw)
    return Inputs(**base)


def make_deck(**kw) -> DeckTerms:
    d = DeckTerms("deck.pptx", slide_count=3)
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def dref(loc, label=""):
    return SourceRef("deck.pptx", loc, label)


def make_review(cap: CapTable) -> Review:
    rv = Review()
    rv.derived.update(basic_before=10000.0, fd_before=12000.0, pre_round_basic=8000.0, pre_round_fd=10000.0,
                      committed_cap=cap.round_cash_existing.value + cap.round_cash_commitments.value)
    return rv


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    """.env may hold a live RESEND_API_KEY; no test may send a real email."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
