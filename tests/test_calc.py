import pytest

from captable_app.calc import NEW_INVESTOR, UNCOUNTED, CalculationBlocked, calculate
from captable_app.models import Figure

from conftest import make_cap, make_inputs, ref


def _row(res, name=None, rtype=None):
    return next(r for r in res.rows if (name and r.name == name) or (rtype and r.row_type == rtype))


# ---- commitments already included vs excluded --------------------------------------

def test_commitments_already_in_before_are_not_added_again():
    res = calculate(make_cap(), make_inputs(commitments_in_before=True))
    commit = _row(res, "Angel Group C")
    assert commit.before_basic == commit.after_basic == 500
    assert commit.adj_commit == 0
    assert not any(r.row_type == UNCOUNTED for r in res.rows)
    # 10,000 - 500 plug released + 500 new
    assert res.totals["after_basic"] == pytest.approx(10000)
    assert res.investor_row.pct_after_basic == pytest.approx(500 / 10000)


def test_commitments_not_in_before_added_as_separate_aggregate_row():
    res = calculate(make_cap(), make_inputs(commitments_in_before=False, uncounted_commitments=1000.0))
    agg = _row(res, rtype=UNCOUNTED)
    assert agg.adj_commit == pytest.approx(1000)          # $1,000 / $1.00
    assert "holders not named" in agg.name
    assert _row(res, "Angel Group C").after_basic == 500   # existing commitment row untouched
    assert res.totals["after_basic"] == pytest.approx(10000 - 500 + 1000 + 500)
    assert res.investor_row.pct_after_basic == pytest.approx(500 / 11000)
    assert res.valuation["proceeds_uncounted"] == 1000


def test_commitments_not_in_before_without_amount_is_blocked():
    with pytest.raises(CalculationBlocked) as e:
        calculate(make_cap(), make_inputs(commitments_in_before=False, uncounted_commitments=None))
    assert "uncounted commitment amount" in str(e.value)


# ---- basic vs fully diluted ---------------------------------------------------------

def test_basic_excludes_options_and_pool_fully_diluted_includes_them():
    res = calculate(make_cap(), make_inputs())
    opt = _row(res, "Other common holders")
    pool = _row(res, rtype="pool")
    assert (opt.before_basic, opt.before_fd) == (0, 1000)
    assert (pool.before_basic, pool.before_fd) == (0, 1000)
    assert res.totals["before_basic"] == 10000 and res.totals["before_fd"] == 12000
    iv = res.investor_row
    assert iv.pct_after_basic == pytest.approx(500 / 10000)
    assert iv.pct_after_fd == pytest.approx(500 / 12000)
    pool_cls = next(c for c in res.classes if c.key == "POOL")
    assert pool_cls.pct_before_basic is None and pool_cls.pct_after_fd == pytest.approx(1000 / 12000)


def test_same_treatment_before_and_after_and_percentages_sum_to_one():
    res = calculate(make_cap(), make_inputs())
    assert sum(r.pct_before_basic for r in res.rows) == pytest.approx(1)
    assert sum(r.pct_after_fd for r in res.rows) == pytest.approx(1)
    assert sum(c.after for c in res.classes) == pytest.approx(res.totals["after_fd"])


def test_percentage_point_change_is_after_minus_before():
    res = calculate(make_cap(), make_inputs(check_size=2000.0))
    f = _row(res, "Founder")
    assert f.delta_fd == pytest.approx(6000 / 13500 - 6000 / 12000)


# ---- unsold plug row -------------------------------------------------------------------

def test_placeholder_release_vs_keep():
    rel = calculate(make_cap(), make_inputs(placeholder_mode="release"))
    keep = calculate(make_cap(), make_inputs(placeholder_mode="keep"))
    assert _row(rel, "Remaining Round Planned").after_basic == 0
    assert _row(keep, "Remaining Round Planned").after_basic == 500
    assert keep.totals["after_basic"] == rel.totals["after_basic"] + 500
    assert keep.valuation["proceeds_open_kept"] == 500 and rel.valuation["proceeds_open_kept"] == 0


# ---- source reconciliation -------------------------------------------------------------

def test_source_total_reconciliation_passes_and_detects_difference():
    ok = calculate(make_cap(), make_inputs())
    assert all(passed for name, passed, _ in ok.checks if "ties to source" in name)
    bad = calculate(make_cap(source_total_basic=Figure(9990.0, ref("Intermediate!N74"))), make_inputs())
    chk = next(c for c in bad.checks if c[0] == "Before outstanding ties to source")
    assert chk[1] is False and "9,990" in chk[2]


def test_class_total_reconciliation_detects_mismatch():
    cap = make_cap()
    cap.source_class_totals["PS1"] = [Figure(2001.0, ref("Intermediate!E72"))]
    res = calculate(cap, make_inputs())
    assert next(c for c in res.checks if c[0] == "Class totals tie to source")[1] is False


# ---- missing / invalid values --------------------------------------------------------

@pytest.mark.parametrize("kw", [dict(check_size=None), dict(check_size=0.0), dict(check_size=-5.0),
                                dict(share_price=None), dict(share_price=0.0)])
def test_missing_or_impossible_inputs_block_rather_than_default_to_zero(kw):
    with pytest.raises(CalculationBlocked):
        calculate(make_cap(), make_inputs(**kw))


def test_missing_list_blocks():
    with pytest.raises(CalculationBlocked) as e:
        calculate(make_cap(), make_inputs(missing=["Check size: ambiguous"]))
    assert e.value.missing == ["Check size: ambiguous"]


def test_new_shares_are_not_rounded_and_fraction_is_flagged():
    res = calculate(make_cap(), make_inputs(check_size=100.0, share_price=0.8293))
    assert res.new_shares == 100.0 / 0.8293
    assert next(c for c in res.checks if c[0] == "Fractional new-investor shares")[1] is False


# ---- valuation -------------------------------------------------------------------------

def test_post_money_is_pre_plus_modelled_proceeds_and_bridge_closes():
    res = calculate(make_cap(), make_inputs(pre_money=8000.0, check_size=500.0))
    v = res.valuation
    assert v["proceeds"] == 1000 + 500 + 500          # issued + commitment rows + this check
    assert v["post_money"] == 8000 + 2000
    assert v["implied_pre_basic"] == 8000              # $1 x pre-round outstanding (10,000 - 2,000 Seed-3)
    assert v["implied_pre_fd"] == 10000
    assert v["implied_post_basic"] == 10000
    assert sum(x for _, x in res.post_bridge) == pytest.approx(v["implied_post_basic"] - v["post_money"])
    assert res.post_bridge[-1][1] == pytest.approx(0)


def test_new_investor_row_is_distinct():
    res = calculate(make_cap(), make_inputs(investor="Acme Ventures"))
    assert res.rows[-1].row_type == NEW_INVESTOR and res.rows[-1].name == "Acme Ventures"
    assert res.rows[-1].before_fd == 0
