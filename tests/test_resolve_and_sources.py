"""Input resolution with missing / conflicting source figures, and source-review detections."""
from captable_app.extract_xlsx import Cell, WorkbookDump
from captable_app.models import Figure
from captable_app.normalize import parse_money
from captable_app.resolve import resolve_inputs
from captable_app.validate import find_cycles

from conftest import dref, make_cap, make_deck, make_review


def _resolve(cap=None, deck=None, **kw):
    cap = cap or make_cap()
    deck = deck or make_deck()
    rv = make_review(cap)
    args = dict(investor=None, check_size=None, share_price=None, commitments_in_before=None,
                uncounted_commitments=None, placeholder_mode="release", pre_money=None)
    args.update(kw)
    return resolve_inputs(cap=cap, deck=deck, review=rv, **args), rv


def test_conflicting_open_allocation_requires_check_size():
    deck = make_deck(open_allocation=[Figure(450.0, dref("Slide 19", "Open to New Investors: $450"))])
    inp, _ = _resolve(deck=deck, commitments_in_before="yes")
    assert inp.check_size is None
    assert any(m.startswith("Check size") and "$450.00" in m and "$500.00" in m for m in inp.missing)


def test_unambiguous_open_allocation_used_with_source():
    deck = make_deck(open_allocation=[Figure(500.0, dref("Slide 19", "Open to New Investors: $500"))])
    inp, _ = _resolve(deck=deck, commitments_in_before="yes")
    assert inp.check_size == 500 and not inp.missing
    src = next(x.source for x in inp.resolved if x.name == "Check size")
    assert "Slide 19" in src and "Summary!F13" in src


def test_share_price_defaults_to_cap_table_and_user_override_is_flagged():
    inp, _ = _resolve(check_size=100.0, commitments_in_before="yes")
    assert inp.share_price == 1.0
    assert "Intermediate!H76" in next(x.source for x in inp.resolved if x.name == "Share price")
    inp2, rv = _resolve(check_size=100.0, share_price=1.25, commitments_in_before="yes")
    assert inp2.share_price == 1.25 and any(i.code == "U01" for i in rv.issues)


def test_missing_issue_price_blocks():
    inp, _ = _resolve(cap=make_cap(issue_price=None), check_size=100.0, commitments_in_before="yes")
    assert any(m.startswith("Share price") for m in inp.missing)


def test_commitment_treatment_auto_only_when_sources_agree():
    agree = make_deck(committed=[Figure(1500.0, dref("Slide 19", "Committed: $1,500"))])
    inp, _ = _resolve(deck=agree, check_size=100.0)
    assert inp.commitments_in_before is True and not inp.missing
    conflict = make_deck(committed=[Figure(2400.0, dref("Slide 19", "Committed: $2,400"))])
    inp2, _ = _resolve(deck=conflict, check_size=100.0)
    assert inp2.commitments_in_before is None
    assert any(m.startswith("Commitments treatment") for m in inp2.missing)


def test_commitments_no_requires_amount():
    inp, _ = _resolve(check_size=100.0, commitments_in_before="no")
    assert any(m.startswith("Uncounted commitments") for m in inp.missing)
    inp2, _ = _resolve(check_size=100.0, commitments_in_before="no", uncounted_commitments=250.0)
    assert not inp2.missing and inp2.uncounted_commitments == 250.0


def test_conflicting_deck_pre_money_requires_input():
    deck = make_deck(pre_money=[Figure(9.2e6, dref("Slide 2")), Figure(9.5e6, dref("Slide 19"))])
    inp, _ = _resolve(deck=deck, check_size=100.0, commitments_in_before="yes")
    assert any(m.startswith("Pre-money") for m in inp.missing)


def test_parse_money_units():
    assert parse_money("9.2", "M") == 9_200_000
    assert parse_money("900", "K") == 900_000
    assert parse_money("1,250,000", None) == 1_250_000


def test_circular_reference_detection():
    cells = {("S", "A1"): Cell("S", "A1", "=B1+1", 0), ("S", "B1"): Cell("S", "B1", "=SUM(A1:A2)", 0),
             ("S", "C1"): Cell("S", "C1", "=D1", 0), ("S", "D1"): Cell("S", "D1", None, 5)}
    wb = WorkbookDump("x.xlsx", {"S": "visible"}, cells, {})
    cycles = find_cycles(wb)
    assert cycles and {"S!A1", "S!B1"} <= set(cycles[0])
