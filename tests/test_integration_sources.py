"""End-to-end checks on the supplied GridMatrix sources (skipped when they are not present)."""
import pytest

from captable_app.calc import calculate
from captable_app.extract_deck import extract_deck
from captable_app.extract_xlsx import extract_workbook
from captable_app.normalize import parse_cap_table, parse_deck_terms
from captable_app.resolve import resolve_inputs
from captable_app.validate import review_sources

from conftest import CAP_XLSX, DECK_PPTX, real_sources

pytestmark = real_sources


@pytest.fixture(scope="module")
def src():
    wb = extract_workbook(CAP_XLSX)
    cap = parse_cap_table(wb)
    deck = parse_deck_terms(extract_deck(DECK_PPTX))
    return wb, cap, deck, review_sources(wb, cap, deck)


def _inputs(src, **kw):
    _, cap, deck, rv = src
    args = dict(investor=None, check_size=None, share_price=None, commitments_in_before=None,
                uncounted_commitments=None, placeholder_mode="release", pre_money=None)
    args.update(kw)
    return resolve_inputs(cap=cap, deck=deck, review=rv, **args)


def test_before_ties_to_source_totals(src):
    _, cap, _, rv = src
    assert rv.derived["basic_before"] == pytest.approx(cap.source_total_basic.value, abs=0.01)
    assert rv.derived["fd_before"] == pytest.approx(cap.source_total_fd.value, abs=0.01)
    assert next(i for i in rv.issues if i.code == "TIE-CLASS").severity == "INFO"


def test_known_source_errors_detected(src):
    _, _, _, rv = src
    codes = {i.code for i in rv.issues}
    assert {"P01", "M01", "M02", "M03", "P04", "CV1"} <= codes
    assert [i.code for i in rv.top(3)] == ["P01", "M02", "M03"]
    assert any(i.code.startswith("N-IntermediateCapTable") for i in rv.issues)   # broken named ranges


def test_defaults_are_blocked_with_precise_missing_inputs(src):
    inp = _inputs(src)
    assert inp.share_price == 0.8293 and inp.check_size is None
    assert len(inp.missing) == 2
    assert inp.missing[0].startswith("Check size") and inp.missing[1].startswith("Commitments treatment")


def test_explicit_inputs_calculate(src):
    _, cap, _, rv = src
    inp = _inputs(src, check_size=900000.0, commitments_in_before="yes")
    res = calculate(cap, inp, rv.derived)
    assert res.new_shares == pytest.approx(900000 / 0.8293)
    assert res.investor_row.pct_after_basic == pytest.approx(0.070400, abs=1e-6)
    assert res.investor_row.pct_after_fd == pytest.approx(0.061516, abs=1e-6)
    assert res.valuation["post_money"] == pytest.approx(9_200_000 + 1_839_554.1412 + 365_000 + 900_000)


def test_pdf_is_one_page(src, tmp_path):
    import pymupdf
    from captable_app.pdf_report import write_blocked_pdf, write_pdf
    _, cap, deck, rv = src
    inp = _inputs(src, check_size=900000.0, commitments_in_before="yes")
    res = calculate(cap, inp, rv.derived)
    p = tmp_path / "r.pdf"
    write_pdf(str(p), cap, deck, inp, res, rv.top(3))
    assert pymupdf.open(str(p)).page_count == 1
    pb = tmp_path / "b.pdf"
    write_blocked_pdf(str(pb), cap, deck, _inputs(src), rv.top(3), rv.derived)
    with pymupdf.open(str(pb)) as d:
        assert d.page_count == 1 and "Unable to calculate" in d[0].get_text()
