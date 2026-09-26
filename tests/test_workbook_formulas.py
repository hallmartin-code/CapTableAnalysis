"""The workbook must recalculate from its inputs.  Uses the `formulas` engine (skipped if absent)."""
import dataclasses

import pytest

from captable_app.calc import calculate
from captable_app.validate import Review
from captable_app.verify import recalc
from captable_app.workbook import write_workbook

from conftest import make_cap, make_deck, make_inputs

pytest.importorskip("formulas")


@pytest.fixture
def book(tmp_path):
    cap, inp = make_cap(), make_inputs()
    path = str(tmp_path / "t.xlsx")
    layout = write_workbook(path, cap, make_deck(), inp, Review())
    return path, cap, inp, layout


def _a(addr):
    return addr.replace("$", "")


def test_formulas_match_python_model(book):
    path, cap, inp, lay = book
    g = recalc(path)
    res = calculate(cap, inp)
    S = lay["S"]
    assert g("Summary", _a(S["new_sh"])) == pytest.approx(res.new_shares)
    assert g("Summary", _a(S["own_b"])) == pytest.approx(res.investor_row.pct_after_basic)
    assert g("Summary", _a(S["own_f"])) == pytest.approx(res.investor_row.pct_after_fd)
    assert g("Summary", _a(S["post"])) == pytest.approx(res.valuation["post_money"])
    assert g("Summary", _a(S["n_err"])) == 0


@pytest.mark.parametrize("changes,kw", [
    ({"check": 1500.0}, dict(check_size=1500.0)),
    ({"price": 2.0}, dict(share_price=2.0)),
    ({"cib": "no", "unc": 300.0}, dict(commitments_in_before=False, uncounted_commitments=300.0)),
    ({"ph": "keep"}, dict(placeholder_mode="keep")),
])
def test_changing_inputs_updates_dependent_formulas(book, changes, kw):
    path, cap, inp, lay = book
    S = lay["S"]
    g = recalc(path, {("Summary", _a(S[k])): v for k, v in changes.items()})
    res = calculate(cap, dataclasses.replace(inp, **kw))
    assert g("Summary", _a(S["own_b"])) == pytest.approx(res.investor_row.pct_after_basic)
    assert g("Summary", _a(S["own_f"])) == pytest.approx(res.investor_row.pct_after_fd)
    assert g("Summary", _a(S["post"])) == pytest.approx(res.valuation["post_money"])
    for i, c in enumerate(res.classes):
        assert g("Summary", f"E{lay['cls_first'] + i}") == pytest.approx(c.after)
    assert g("Summary", _a(S["n_err"])) == 0


def test_negative_allocation_is_flagged(book):
    path, cap, inp, lay = book
    S = lay["S"]
    g = recalc(path, {("Summary", _a(S["check"])): -100.0})
    assert g("Summary", _a(S["own_b"])) == "BLOCKED"
    assert g("Summary", _a(S["n_err"])) >= 1


def test_source_total_mismatch_shows_error(tmp_path):
    from captable_app.models import Figure
    from conftest import ref
    cap = make_cap(source_total_basic=Figure(9990.0, ref("Intermediate!N74")))
    path = str(tmp_path / "bad.xlsx")
    lay = write_workbook(path, cap, make_deck(), make_inputs(), Review())
    g = recalc(path)
    assert g("Summary", _a(lay["S"]["n_err"])) >= 1
