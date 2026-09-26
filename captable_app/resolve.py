"""Resolve each calculation input to a value and its exact source, or record why it is missing."""
from __future__ import annotations

from typing import Optional

from .fmt import usd
from .models import CapTable, DeckTerms, Inputs, Issue, ResolvedInput
from .validate import Review, TOL_USD, _distinct, _locs


def _ai(f) -> bool:
    """Figure read from an image by Claude: may raise a conflict, never resolves an input by itself."""
    return str(getattr(f, "note", "")).startswith("ai_image")


def resolve_inputs(*, investor: Optional[str], check_size: Optional[float], share_price: Optional[float],
                   commitments_in_before: Optional[str], uncounted_commitments: Optional[float],
                   placeholder_mode: str, pre_money: Optional[float],
                   cap: CapTable, deck: DeckTerms, review: Review) -> Inputs:
    res: list[ResolvedInput] = []
    missing: list[str] = []

    name = investor or "New investor"
    res.append(ResolvedInput("Investor", name, "User input (--investor)" if investor else "Default ('New investor')"))

    # Share price ----------------------------------------------------------------------
    price = None
    if share_price is not None:
        price = share_price
        src = "User input (--share-price)"
        if cap.issue_price and abs(share_price - cap.issue_price.value) > 1e-9:
            src += f"; differs from cap-table issue price {cap.issue_price.value:g} at {cap.issue_price.ref}"
            review.issues.append(Issue("U01", "MEDIUM", "Assumption", "User share price overrides cap-table issue price",
                                       f"--share-price {share_price:g} vs {cap.issue_price.value:g} "
                                       f"({cap.issue_price.ref.location}).", priority=9))
        res.append(ResolvedInput("Share price", share_price, src))
    elif cap.issue_price:
        price = cap.issue_price.value
        res.append(ResolvedInput("Share price", price, f"{cap.issue_price.ref} (explicit Seed-3 issue price; "
                                                       "cap table is the default pricing source)"))
    else:
        missing.append("Share price: no issue price for the round class found in the cap table; supply --share-price.")

    # Check size -----------------------------------------------------------------------
    chk = None
    if check_size is not None:
        chk = check_size
        res.append(ResolvedInput("Check size", chk, "User input (--check-size)"))
    else:
        cands = list(deck.open_allocation) + ([cap.round_cash_open] if cap.round_cash_open else [])
        vals = _distinct(cands, TOL_USD)
        if len(vals) == 1 and any(not _ai(f) for f in cands):
            chk = vals[0]
            res.append(ResolvedInput("Check size", chk, "Full open allocation, stated consistently at: " + _locs(cands)))
        elif not vals:
            missing.append("Check size: not supplied and no open allocation is stated in the deck or cap table; "
                           "supply --check-size.")
        else:
            missing.append("Check size: not supplied, and the open allocation is ambiguous: "
                           + "; ".join(f"{usd(f.value)} at {f.ref}" for f in cands)
                           + ". Supply --check-size.")

    # Commitments --------------------------------------------------------------------
    cib: Optional[bool] = None
    committed_cap = review.derived.get("committed_cap")
    if commitments_in_before is not None:
        cib = commitments_in_before.lower() == "yes"
        res.append(ResolvedInput("Commitments already in Before", "yes" if cib else "no",
                                 "User input (--commitments-in-before)"))
    else:
        deck_vals = _distinct(deck.committed, TOL_USD)
        if (committed_cap is not None and any(not _ai(f) for f in deck.committed)
                and all(abs(v - committed_cap) <= TOL_USD for v in deck_vals)):
            cib = True
            res.append(ResolvedInput("Commitments already in Before", "yes",
                                     f"Deck committed ({_locs(deck.committed)}) equals cap-table issued + commitment "
                                     f"rows {usd(committed_cap)}"))
        else:
            detail = (f"deck states {_locs(deck.committed)} but the cap table's issued + commitment rows total "
                      f"{usd(committed_cap)}") if committed_cap is not None and deck_vals else \
                "the sources do not state it"
            missing.append("Commitments treatment: whether all existing Seed-3 commitments are already in the pro "
                           f"forma is not established ({detail}). Set --commitments-in-before yes|no "
                           "(with 'no', also --uncounted-commitments USD).")
    unc = None
    if cib is False:
        if uncounted_commitments is None:
            missing.append("Uncounted commitments: --commitments-in-before no requires --uncounted-commitments "
                           "(USD amount of Seed-3 commitments not in the cap table, priced at the issue price).")
        else:
            unc = uncounted_commitments
            res.append(ResolvedInput("Commitments not in Before (USD)", unc, "User input (--uncounted-commitments)"))

    # Placeholder --------------------------------------------------------------------
    if cap.rows_of("placeholder"):
        ph = cap.rows_of("placeholder")[0]
        res.append(ResolvedInput("Unsold allocation plug row", placeholder_mode,
                                 f"'{ph.name}' ({cap.extras['detail_sheet']} row {ph.source_row}); "
                                 f"--open-allocation-placeholder {placeholder_mode}"
                                 + (" (default)" if placeholder_mode == "release" else "")))

    # Pre-money ----------------------------------------------------------------------
    pm = None
    if pre_money is not None:
        pm = pre_money
        res.append(ResolvedInput("Pre-money valuation", pm, "User input (--pre-money)"))
    else:
        vals = _distinct(deck.pre_money, TOL_USD)
        if len(vals) == 1 and any(not _ai(f) for f in deck.pre_money):
            pm = vals[0]
            res.append(ResolvedInput("Pre-money valuation", pm, "Deck: " + _locs(deck.pre_money)))
        elif len(vals) > 1:
            missing.append("Pre-money: the deck states conflicting figures (" + _locs(deck.pre_money)
                           + "); supply --pre-money.")
        elif price:
            pm = price * review.derived["pre_round_basic"]
            res.append(ResolvedInput("Pre-money valuation", pm,
                                     f"Not stated; implied = price x pre-round outstanding shares "
                                     f"({review.derived['pre_round_basic']:,.2f}) - outstanding basis, not fully diluted"))

    return Inputs(name, chk, price, cib, unc, placeholder_mode, pm, res, missing)
