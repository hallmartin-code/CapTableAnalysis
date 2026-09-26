"""Source review: workbook integrity, cap-table tie-outs and deck-vs-cap-table comparison.

Every finding records both values, their exact locations and the arithmetic.
Nothing here modifies the source figures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from openpyxl.utils import column_index_from_string, get_column_letter

from .extract_xlsx import ERROR_VALUES, WorkbookDump
from .fmt import pct, sh, usd, usd0
from .models import CapTable, DeckTerms, Figure, Issue

TOL_SHARES = 0.01
TOL_USD = 1.0


@dataclass
class Comparison:
    item: str
    deck: str
    cap: str
    status: str            # MATCH / MISMATCH / NOT IN DECK / NOT IN CAP TABLE
    used: str


@dataclass
class Review:
    issues: list[Issue] = field(default_factory=list)
    comparisons: list[Comparison] = field(default_factory=list)
    derived: dict = field(default_factory=dict)       # implied figures reused downstream

    def add(self, *a, **k):
        self.issues.append(Issue(*a, **k))

    def top(self, n: int = 3) -> list[Issue]:
        return sorted((i for i in self.issues if i.severity != "INFO"), key=lambda i: i.rank)[:n]


def _locs(figs: list[Figure]) -> str:
    return "; ".join(f"{f.ref.location} \"{f.ref.label}\"" for f in figs)


def _distinct(figs: list[Figure], tol: float) -> list[float]:
    vals: list[float] = []
    for f in figs:
        if all(abs(f.value - v) > tol for v in vals):
            vals.append(f.value)
    return vals


# --------------------------------------------------------------------------------------

def review_sources(wb: WorkbookDump, cap: CapTable, deck: DeckTerms) -> Review:
    rv = Review()
    _workbook_integrity(wb, cap, rv)
    _cap_table_checks(wb, cap, rv)
    _deck_vs_cap(cap, deck, rv)
    return rv


# ---------------------------------------------------------------- workbook integrity

REF_RE = re.compile(r"(?:(?:'([^']+)'|([A-Za-z_][\w .]*?))!)?\$?([A-Z]{1,3})\$?(\d+)(?::\$?([A-Z]{1,3})\$?(\d+))?")


def formula_refs(sheet: str, formula: str) -> set[tuple[str, str]]:
    """Cells referenced by a formula (ranges expanded)."""
    refs = set()
    body = re.sub(r'"[^"]*"', "", formula)
    for m in REF_RE.finditer(body):
        sh_name = m.group(1) or m.group(2) or sheet
        c1, r1 = m.group(3), int(m.group(4))
        c2, r2 = (m.group(5), int(m.group(6))) if m.group(5) else (c1, r1)
        for ci in range(column_index_from_string(c1), column_index_from_string(c2) + 1):
            for r in range(r1, r2 + 1):
                refs.add((sh_name.strip(), f"{get_column_letter(ci)}{r}"))
    return refs


def find_cycles(wb: WorkbookDump) -> list[list[str]]:
    graph = {k: formula_refs(k[0], c.formula) for k, c in wb.cells.items() if c.is_formula}
    WHITE, GREY, BLACK = 0, 1, 2
    color = {k: WHITE for k in graph}
    cycles = []

    def dfs(n, path):
        color[n] = GREY
        for m in graph.get(n, ()):
            if m not in graph:
                continue
            if color[m] == GREY:
                i = path.index(m) if m in path else 0
                cycles.append([f"{s}!{c}" for s, c in path[i:] + [m]])
            elif color[m] == WHITE:
                dfs(m, path + [m])
        color[n] = BLACK

    import sys
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))
    for n in graph:
        if color[n] == WHITE:
            dfs(n, [n])
    return cycles


def _workbook_integrity(wb: WorkbookDump, cap: CapTable, rv: Review) -> None:
    hidden = [s for s, st in wb.sheets.items() if st != "visible"]
    hid_rc = {s: (wb.hidden_rows.get(s), wb.hidden_cols.get(s)) for s in wb.sheets
              if wb.hidden_rows.get(s) or wb.hidden_cols.get(s)}
    rv.add("X01", "INFO", "Extraction", "Workbook inventory",
           f"Sheets: {', '.join(f'{s} ({st})' for s, st in wb.sheets.items())}. Hidden sheets: "
           f"{', '.join(hidden) or 'none'}. Hidden rows/columns: {hid_rc or 'none'}. "
           f"{sum(1 for c in wb.cells.values() if c.is_formula)} formula cells and "
           f"{sum(1 for c in wb.cells.values() if not c.is_formula)} constant cells read. Defined names: "
           + "; ".join(f"{n} -> {t}" for n, t in wb.defined_names.items()), priority=90)

    errs = [f"{c.sheet}!{c.coord} = {c.value}" for c in wb.cells.values()
            if isinstance(c.value, str) and c.value.strip() in ERROR_VALUES]
    ref_errs = [f"{c.sheet}!{c.coord}" for c in wb.cells.values() if c.is_formula and "#REF!" in c.formula]
    missing = [f"{c.sheet}!{c.coord}" for c in wb.cells.values() if c.is_formula and c.value is None]
    if errs or ref_errs:
        rv.add("F01", "HIGH", "Formula", "Formula error values in source",
               "Cells showing Excel error values or #REF! references: " + ", ".join(errs + ref_errs),
               refs=errs + ref_errs, resolution="Affected figures are not used without confirmation.", priority=5)
    else:
        rv.add("F01", "INFO", "Formula", "No Excel error values found",
               "No #REF!, #DIV/0!, #VALUE!, #NAME?, #N/A, #NUM! or #NULL! results or references in any cell.",
               priority=95)
    if missing:
        rv.add("F02", "MEDIUM", "Formula", "Formulas without cached results",
               f"{len(missing)} formula cells have no stored result (file saved without recalculation): "
               + ", ".join(missing[:20]), refs=missing[:20], priority=30)
    cycles = find_cycles(wb)
    if cycles:
        rv.add("F03", "HIGH", "Formula", "Circular reference", "Cycle(s): " +
               " | ".join(" -> ".join(c) for c in cycles[:5]), priority=6)
    else:
        rv.add("F03", "INFO", "Formula", "No circular references detected",
               "Dependency graph of all formula cells (ranges expanded) contains no cycles.", priority=96)

    # Named ranges pointing at blank or label cells
    for n, target in wb.defined_names.items():
        m = re.match(r"'?([^'!]+)'?!\$?([A-Z]+)\$?(\d+)$", target or "")
        if not m:
            continue
        cell = wb.get(m.group(1), f"{m.group(2)}{m.group(3)}")
        if cell is None or not isinstance(cell.value, (int, float)):
            row_label = wb.value(m.group(1), f"B{m.group(3)}")
            rv.add(f"N-{n}", "MEDIUM", "Formula", f"Named range '{n}' points to a non-numeric cell",
                   f"'{n}' refers to {target}, which is "
                   f"{'blank' if cell is None else repr(cell.value)} (row label: {row_label!r}). "
                   "Any consumer of this name would read an empty value instead of the intended total.",
                   refs=[target], resolution="The app does not use this name; totals are read from the labelled "
                                             "total cells directly.", priority=40)

    # Hard-coded values and inconsistent SUM ranges in totals rows
    sheet = cap.extras["detail_sheet"]
    lr = cap.extras["label_rows"]
    for label in ("fully diluted shares", "total shares outstanding"):
        r = lr.get(label)
        if not r:
            continue
        rowcells = [c for c in wb.sheet_cells(sheet) if int(re.search(r"\d+", c.coord).group()) == r
                    and isinstance(c.value, (int, float))]
        consts = [f"{c.coord}={sh(c.value)}" for c in rowcells if not c.is_formula and c.value]
        ends = {}
        for c in rowcells:
            if c.is_formula:
                m = re.search(r"SUM\(\$?[A-Z]+\$?(\d+):\$?[A-Z]+\$?(\d+)\)", c.formula)
                if m:
                    ends.setdefault((int(m.group(1)), int(m.group(2))), []).append(c.coord)
        msg = []
        if consts:
            msg.append(f"hard-coded constants instead of formulas: {', '.join(consts)}")
        if len(ends) > 1:
            msg.append("SUM ranges differ within the row: " + "; ".join(
                f"rows {a}-{b} in {', '.join(v)}" for (a, b), v in ends.items()))
        if msg:
            rv.add(f"T-{r}", "LOW", "Totals", f"Totals row '{sheet}!{r}' ({label}) is partly hard-coded",
                   f"{sheet} row {r}: " + "; ".join(msg) + ". Hard-coded totals do not update if holder rows change. "
                   "The app re-sums every row independently and compares (see tie-out checks).",
                   refs=[f"{sheet}!{r}"], priority=60)
    # Other hard-coded aggregates on stakeholder rows (e.g. FD column not a formula while OUT is)
    cols = cap.extras["cols"]
    for row in cap.rows:
        fd = wb.get(sheet, f"{cols['fd']}{row.source_row}") if cols["fd"] else None
        out = wb.get(sheet, f"{cols['out']}{row.source_row}") if cols["out"] else None
        if fd and out and out.is_formula and not fd.is_formula:
            rv.add(f"T-row{row.source_row}", "LOW", "Totals",
                   f"{sheet}!{fd.coord} is a hard-coded constant",
                   f"'{row.name}': outstanding {out.coord} is a formula ({out.formula}) but fully diluted "
                   f"{fd.coord} is typed in as {sh(fd.value)}. Independent sum of the row = "
                   f"{sh(row.fully_diluted(cap.classes))}.", refs=[f"{sheet}!{fd.coord}"], priority=61)


# ---------------------------------------------------------------- cap table checks

def _cap_table_checks(wb: WorkbookDump, cap: CapTable, rv: Review) -> None:
    sheet = cap.extras["detail_sheet"]
    rc = cap.round_class
    price = cap.issue_price.value if cap.issue_price else None
    basic = sum(r.basic(cap.classes) for r in cap.rows)
    fd = sum(r.fully_diluted(cap.classes) for r in cap.rows)
    rv.derived.update(basic_before=basic, fd_before=fd)

    # Source-total tie-out
    for label, mine, figs in (("Issued and outstanding (basic)", basic, [cap.source_total_basic]),
                              ("Fully diluted", fd, [cap.source_total_fd, cap.source_total_fd_alt])):
        for f in filter(None, figs):
            d = mine - f.value
            rv.add(f"TIE-{f.ref.location}", "INFO" if abs(d) <= TOL_SHARES else "HIGH", "Totals",
                   f"{label} total tie-out vs {f.ref.location}: {'ties' if abs(d) <= TOL_SHARES else 'DOES NOT TIE'}",
                   f"Source {f.ref.location} = {sh(f.value)}; independent sum of all {len(cap.rows)} parsed rows "
                   f"= {sh(mine)}; difference = {sh(d)}.", refs=[f.ref.location],
                   priority=2 if abs(d) > TOL_SHARES else 97)

    # Class tie-out
    bad = []
    for c in cap.classes:
        mine = sum(r.shares.get(c.key, 0.0) for r in cap.rows)
        for f in cap.source_class_totals.get(c.key, []):
            if abs(mine - f.value) > TOL_SHARES:
                bad.append(f"{c.key}: source {f.ref.location}={sh(f.value)} vs independent {sh(mine)}")
    opt_pool = sum(r.shares.get("OPT", 0) + r.shares.get("POOL", 0) for r in cap.rows)
    for f in cap.source_class_totals.get("OPT+POOL", []):
        if abs(opt_pool - f.value) > TOL_SHARES:
            bad.append(f"Options+pool: source {f.ref.location}={sh(f.value)} vs independent {sh(opt_pool)}")
    rv.add("TIE-CLASS", "HIGH" if bad else "INFO", "Totals",
           "Class totals " + ("do not reconcile" if bad else "reconcile to every source total"),
           "; ".join(bad) if bad else "Each class sum over stakeholder rows equals the Intermediate FD-row, "
           "outstanding-row and Summary-tab totals: " + "; ".join(
               f"{c.key} {sh(sum(r.shares.get(c.key, 0.0) for r in cap.rows))}" for c in cap.classes),
           priority=3 if bad else 98)

    # 1:1 conversion check
    conv_bad = []
    for c in cap.classes:
        if c.kind == "preferred" and c.conversion_col:
            for r in cap.rows:
                raw = wb.value(sheet, f"{c.source_col}{r.source_row}")
                conv = wb.value(sheet, f"{c.conversion_col}{r.source_row}")
                if isinstance(raw, (int, float)) and isinstance(conv, (int, float)) and abs(raw - conv) > TOL_SHARES:
                    conv_bad.append(f"{sheet}!{c.source_col}{r.source_row} {sh(raw)} vs {c.conversion_col}{r.source_row} {sh(conv)}")
    if conv_bad:
        rv.add("CONV", "HIGH", "Totals", "Preferred shares do not convert 1:1", "; ".join(conv_bad[:10]), priority=4)

    # Seed-3 price divisor embedded in a formula
    fdf = cap.extras.get("round_fd_formula")
    if fdf and price and abs(fdf["divisor"] - price) > 1e-9:
        cash = sum(fdf["cash_terms"])
        at_div, at_price = cash / fdf["divisor"], cash / price
        ratios = "; ".join(f"{k} price {p.value:g} = {price:g} x {p.value / price:.4f} (= {fdf['divisor']:g} x "
                           f"{p.value / fdf['divisor']:.4f})" for k, p in cap.issue_prices.items() if k != rc)
        ph = cap.rows_of("placeholder")
        ph_note = ""
        if ph and cap.round_cash_open:
            ph_src = ph[0].shares[rc]
            ph_price = cap.round_cash_open.value / price
            ph_col = cap.cls(rc).conversion_col or cap.cls(rc).source_col
            ph_note = (f" The plug row '{ph[0].name}' ({sheet}!{ph_col}{ph[0].source_row}) inherits the error: "
                       f"{sh(ph_src)} shares in the source vs {usd0(cap.round_cash_open.value)} / {price:g} = "
                       f"{sh(ph_price)} at the issue price.")
            rv.derived["placeholder_at_price"] = ph_price
        transposed = sorted(f"{fdf['divisor']:g}") == sorted(f"{price:g}")
        rv.add("P01", "HIGH", "Formula",
               f"Seed-3 share formula divides by ${fdf['divisor']:g}, not the ${price:g} issue price",
               f"{fdf['cell']} = {fdf['formula']} divides new Seed-3 cash by {fdf['divisor']:g}, but the Seed-3 "
               f"original issue price in {cap.issue_price.ref.location} is {price:g}"
               f"{' (same digits, transposed)' if transposed else ''}. "
               f"Supporting price relationships: {ratios}.{ph_note} Source totals (Summary Seed-3 "
               f"{sh(cap.source_class_totals[rc][0].value)}, FD {sh(cap.source_total_fd.value)}) embed the "
               f"divisor figure.",
               refs=[fdf["cell"], cap.issue_price.ref.location],
               arithmetic=f"{usd0(cash)} / {fdf['divisor']:g} = {sh(at_div)} shares; {usd0(cash)} / {price:g} = "
                          f"{sh(at_price)} shares; difference {sh(at_price - at_div)} shares.",
               resolution=f"New-investor shares are priced at the explicit cap-table issue price {price:g} "
                          f"({cap.issue_price.ref.location}). The source Before table is kept exactly as reported "
                          f"(not repaired); the affected plug row is shown separately and released in After.",
               priority=1)

    # Existing named Seed-3 shares vs formula constant and vs recorded cash
    named = sum(r.shares.get(rc, 0.0) for r in cap.rows_of("holder", "aggregate"))
    rv.derived["round_named_existing"] = named
    if fdf and abs(named - fdf["existing_shares"]) > TOL_SHARES:
        rv.add("P02", "HIGH", "Totals", "Seed-3 existing-share constant does not match holder rows",
               f"{fdf['cell']} adds {sh(fdf['existing_shares'])}; named holders sum to {sh(named)}.", priority=7)
    if price and cap.round_cash_existing:
        implied = named * price
        d = implied - cap.round_cash_existing.value
        if abs(d) > TOL_USD:
            rv.add("P03", "MEDIUM", "Mismatch", "Issued Seed-3 shares x price does not equal recorded Seed-3 cash",
                   f"Named Seed-3 holders ({sheet} rows with stakeholder IDs) hold {sh(named)} shares. At "
                   f"{price:g} that is {usd(implied)}, but the cash term in {cap.round_cash_existing.ref.location} "
                   f"is {usd(cap.round_cash_existing.value)}. The source does not explain the gap (it may reflect "
                   "converted instruments or a different price for some holders; not assumed).",
                   refs=[cap.round_cash_existing.ref.location, cap.issue_price.ref.location],
                   arithmetic=f"{sh(named)} x {price:g} = {usd(implied)}; minus {usd(cap.round_cash_existing.value)} "
                              f"= {usd(d)}",
                   resolution="Post-money on the stated basis uses recorded cash; the implied priced post-money "
                              "uses shares x price. Both are shown and the gap is itemised.", priority=12)

    # Placeholder / unsold allocation counted as outstanding
    for ph in cap.rows_of("placeholder"):
        c = wb.get(sheet, f"{cap.cls(rc).conversion_col or cap.cls(rc).source_col}{ph.source_row}")
        rv.add("P04", "HIGH", "Assumption", f"Unsold allocation '{ph.name}' is counted as issued Seed-3 stock",
               f"{sheet} row {ph.source_row} '{ph.name}' holds {sh(ph.shares[rc])} Seed-3 shares "
               f"(formula {c.formula if c and c.formula else c.value if c else ''}), a plug for the unsold part of "
               f"the round. The source includes it in outstanding ({cap.source_total_basic.ref.location}) and fully "
               f"diluted totals, and Summary 'Cash Raised' includes its "
               f"{usd0(cap.round_cash_open.value) if cap.round_cash_open else 'cash'} although it is not raised. "
               "Adding a new investor's shares on top of it would double-count the open allocation.",
               refs=[f"{sheet}!B{ph.source_row}", f"{sheet}!{c.coord if c else ''}"],
               resolution="Before keeps the row exactly as sourced (so totals tie). By default "
                          "(--open-allocation-placeholder release) a separate adjustment removes it in After and the "
                          "new investor's shares are added at the issue price; 'keep' leaves it in and adds the "
                          "investor on top (double-count risk).", priority=5)

    # Commitment rows identified in Before
    commits = cap.rows_of("commitment")
    if commits:
        rows_txt = "; ".join(
            f"'{r.name}' ({sheet}!{r.source_row}) {sh(r.shares[rc])} sh = {usd(r.shares[rc] * price)} at {price:g}"
            for r in commits) if price else ""
        rv.add("C01", "INFO", "Assumption", "Seed-3 commitment rows already in the pro forma",
               f"Rows without stakeholder IDs holding only Seed-3 shares: {rows_txt}. Their dollar amounts match "
               f"terms of {cap.round_cash_total.ref.location if cap.round_cash_total else 'the Summary cash formula'} "
               f"({usd0(cap.round_cash_commitments.value) if cap.round_cash_commitments else 'n/a'}).",
               refs=[f"{sheet}!{r.source_row}" for r in commits], priority=80)

    # Options memo row repeated
    for r, name, v in cap.extras.get("memo_rows", []):
        rv.add("O01", "LOW", "Totals", f"Options repeated on memo row {sheet}!{r}",
               f"'{name}' repeats {sh(v)} options already carried on the aggregate row "
               f"'{next((x.name for x in cap.rows if x.shares.get('OPT') == v), '?')}'. Its outstanding and fully "
               "diluted cells are blank, so the source counts the options once; the app does the same. "
               "Options and RSUs have no named holders in the source.", refs=[f"{sheet}!{r}"], priority=65)

    # Summary sheet totals left at zero, fractional authorised shares, plan size
    summ = cap.extras.get("summary_sheet")
    if summ:
        scols = cap.extras["summary_cols"]
        for label, r in cap.extras["summary_rows"].items():
            low = label.lower()
            if low.startswith("total") and "issued and outstanding" in low and "warrant" not in low:
                kind = "common" if "common" in low else "preferred" if "preferred" in low else None
                if not kind:
                    continue
                expected = sum(sum(x.shares.get(c.key, 0) for x in cap.rows) for c in cap.classes if c.kind == kind)
                zeros = [f"{summ}!{scols[k]}{r}" for k in ("auth", "issued")
                         if k in scols and wb.value(summ, f"{scols[k]}{r}") == 0]
                if zeros and expected:
                    rv.add(f"S-{r}", "LOW", "Totals", f"Summary total row '{label}' shows 0",
                           f"{', '.join(zeros)} = 0, but the {kind} classes above total {sh(expected)} issued shares.",
                           refs=zeros, resolution="Not used; the app re-sums classes.", priority=62)
        if "auth" in scols:
            for label, r in cap.extras["summary_rows"].items():
                v = wb.value(summ, f"{scols['auth']}{r}")
                if isinstance(v, float) and abs(v - round(v)) > 1e-6:
                    rv.add(f"S-auth{r}", "LOW", "Totals", f"Fractional authorised share count on '{label}'",
                           f"{summ}!{scols['auth']}{r} = {sh(v, 6)} authorised shares, which equals the pro forma "
                           "outstanding figure rather than a charter authorisation.",
                           refs=[f"{summ}!{scols['auth']}{r}"], priority=63)
                if "incentive plan" in label.lower() and isinstance(v, (int, float)):
                    plan_used = sum(x.shares.get("OPT", 0) + x.shares.get("POOL", 0) for x in cap.rows)
                    if abs(v - plan_used) > TOL_SHARES:
                        rv.add("S-plan", "LOW", "Totals", "Plan reserve differs from options + unissued pool",
                               f"{summ}!{scols['auth']}{r} '{label}' = {sh(v)}; options outstanding + pool = "
                               f"{sh(plan_used)}; difference {sh(v - plan_used)} (possibly exercised or cancelled "
                               "awards; not stated).", refs=[f"{summ}!{scols['auth']}{r}"], priority=66)
        if cap.round_cash_total and cap.round_cash_open:
            pass  # covered in P04

    # Convertibles with no share equivalents
    if cap.convertibles:
        tot = sum(f.value for f in cap.convertibles)
        zero_cash = [c for c in cap.classes if c.kind == "preferred" and c.key != rc]
        hints = []
        for c in zero_cash:
            p = cap.issue_prices.get(c.key)
            n = sum(r.shares.get(c.key, 0) for r in cap.rows)
            if p:
                hints.append(f"{c.key} {sh(n)} x {p.value:g} = {usd(n * p.value)}")
        rv.add("CV1", "MEDIUM", "Assumption", "Convertibles listed with cash but no share counts",
               f"{'; '.join(f'{f.ref.location} {f.ref.label} {usd(f.value)}' for f in cap.convertibles)} "
               f"(total {usd(tot)}). The source gives no conversion status or share equivalents. For reference only: "
               f"{'; '.join(hints)}. These are close to some instrument amounts, which suggests but does not "
               "establish that they have converted.",
               refs=[f.ref.location for f in cap.convertibles],
               resolution="No share equivalents added to fully diluted counts (none are stated). If any instrument "
                          "is still outstanding, fully diluted totals are understated.", priority=15)

    # Encoding damage in names
    bad_names = [f"{sheet}!{cap.extras['cols']['name']}{r.source_row}" for r in cap.rows if "�" in r.name]
    if bad_names:
        rv.add("E01", "LOW", "Extraction", "Unreadable characters in holder names",
               f"Replacement characters (�) in {', '.join(bad_names)}; names are reproduced as found.",
               refs=bad_names, priority=70)

    # Fractional shares
    frac = [f"'{r.name}' {sh(r.shares[rc], 6)}" for r in cap.rows if abs(r.shares.get(rc, 0) - round(r.shares.get(rc, 0))) > 1e-6]
    rv.add("FR1", "MEDIUM", "Assumption", "No fractional-share convention stated",
           ("Stated convention: " + cap.fractional_convention) if cap.fractional_convention else
           "Neither source states how fractional shares are treated. Fractional source rows: " + (", ".join(frac) or "none")
           + ". New-investor shares are shown unrounded (check / price) and the issued count must be confirmed.",
           resolution="No rounding applied.", priority=20)

    if cap.as_of:
        rv.add("D01", "INFO", "Extraction", "Cap table date",
               f"Cap table header: 'As of {cap.as_of}' ({sheet}!B3); file name says April 2025. Share counts are "
               "as of that date plus the pro forma round rows.", priority=85)


# ---------------------------------------------------------------- deck vs cap table

def _deck_vs_cap(cap: CapTable, deck: DeckTerms, rv: Review) -> None:
    rc = cap.round_class
    price = cap.issue_price.value if cap.issue_price else None
    round_total = sum(r.shares.get(rc, 0) for r in cap.rows)
    pre_basic = rv.derived["basic_before"] - round_total
    pre_fd = rv.derived["fd_before"] - round_total
    rv.derived.update(pre_round_basic=pre_basic, pre_round_fd=pre_fd, round_total_before=round_total)
    committed_cap = None
    if cap.round_cash_existing and cap.round_cash_commitments:
        committed_cap = cap.round_cash_existing.value + cap.round_cash_commitments.value
    rv.derived["committed_cap"] = committed_cap

    # 1 Round size / open allocation
    rs = _distinct(deck.round_size, TOL_USD)
    cap_rs = cap.round_cash_total
    rv.comparisons.append(Comparison(
        "Seed-3 round size", _locs(deck.round_size) or "not stated",
        f"{usd(cap_rs.value)} at {cap_rs.ref.location} (Cash Raised, includes unsold {usd0(cap.round_cash_open.value) if cap.round_cash_open else ''})" if cap_rs else "not stated",
        "MISMATCH" if cap_rs and any(abs(v - cap_rs.value) > TOL_USD for v in rs) else "MATCH",
        "Not needed for the calculation; post-money uses modelled proceeds."))
    if cap_rs and rs:
        rv.add("M01", "HIGH", "Mismatch", "Round size differs between deck and cap table (and within the deck)",
               f"Deck: {_locs(deck.round_size)}. Cap table: {usd(cap_rs.value)} ({cap_rs.ref.location}).",
               refs=[f.ref.location for f in deck.round_size] + [cap_rs.ref.location],
               arithmetic="; ".join(f"{usd0(v)} - {usd(cap_rs.value)} = {usd(v - cap_rs.value)}" for v in rs),
               resolution="Round size is not an input to ownership; no figure is chosen.", priority=4)

    oa = _distinct(deck.open_allocation, TOL_USD)
    cap_oa = cap.round_cash_open
    rv.comparisons.append(Comparison(
        "Seed-3 open allocation", _locs(deck.open_allocation) or "not stated",
        f"{usd(cap_oa.value)} at {cap_oa.ref.location} (term in formula; same amount drives the "
        f"'Remaining Round Planned' plug row)" if cap_oa else "not stated",
        "MISMATCH" if cap_oa and oa and any(abs(v - cap_oa.value) > TOL_USD for v in oa) else
        ("MATCH" if cap_oa and oa else "INCOMPLETE"),
        "Not used as a default check size because the sources disagree; --check-size must be supplied."))
    if cap_oa and oa and any(abs(v - cap_oa.value) > TOL_USD for v in oa):
        rv.add("M02", "HIGH", "Mismatch",
               f"Open allocation: deck {' / '.join(usd0(v) for v in oa)} vs cap table {usd0(cap_oa.value)}",
               f"Deck: {_locs(deck.open_allocation)}. Cap table: {usd(cap_oa.value)} ({cap_oa.ref.location}, "
               f"also the numerator of {cap.extras.get('round_fd_formula', {}).get('cell', 'the Seed-3 share formula')}).",
               refs=[f.ref.location for f in deck.open_allocation] + [cap_oa.ref.location],
               arithmetic="; ".join(f"{usd(cap_oa.value)} - {usd0(v)} = {usd(cap_oa.value - v)}" for v in oa),
               resolution="The full open allocation is not unambiguous, so it is not used as a default check size.",
               priority=2)

    # 4 Committed
    cm = _distinct(deck.committed, TOL_USD)
    rv.comparisons.append(Comparison(
        "Amount closed / committed", _locs(deck.committed) or "not stated",
        (f"{usd(committed_cap)} = issued {usd(cap.round_cash_existing.value)} + commitment rows "
         f"{usd(cap.round_cash_commitments.value)} ({cap.round_cash_existing.ref.location})") if committed_cap else "not derivable",
        "MISMATCH" if committed_cap and any(abs(v - committed_cap) > TOL_USD for v in cm) else "MATCH" if committed_cap and cm else "INCOMPLETE",
        "Commitments in the cap table are already in Before (named rows). Whether the deck's larger figure includes "
        "commitments missing from the cap table is not established; --commitments-in-before must be set."))
    if committed_cap and cm and any(abs(v - committed_cap) > TOL_USD for v in cm):
        rv.add("M03", "HIGH", "Mismatch",
               f"Committed capital: deck {' / '.join(usd0(v) for v in cm)} vs cap table {usd0(committed_cap)}",
               f"Deck: {_locs(deck.committed)}. Cap table: issued {usd(cap.round_cash_existing.value)} + commitment rows "
               f"{usd(cap.round_cash_commitments.value)} = {usd(committed_cap)} ({cap.round_cash_existing.ref.location}). "
               "It is not established whether the difference is commitments missing from the pro forma.",
               refs=[f.ref.location for f in deck.committed] + [cap.round_cash_existing.ref.location],
               arithmetic="; ".join(f"{usd0(v)} - {usd(committed_cap)} = {usd(v - committed_cap)}" for v in cm),
               resolution="The user must state whether all commitments are in Before (--commitments-in-before). "
                          "With 'no', the uncounted amount must be supplied (--uncounted-commitments).",
               priority=3)

    # 2 Pre-money
    pm = _distinct(deck.pre_money, TOL_USD)
    implied_basic = pre_basic * price if price else None
    implied_fd = pre_fd * price if price else None
    rv.derived.update(implied_pre_basic=implied_basic, implied_pre_fd=implied_fd)
    rv.comparisons.append(Comparison(
        "Pre-money valuation", _locs(deck.pre_money) or "not stated",
        f"Not stated. Implied: {price:g} x pre-round outstanding {sh(pre_basic)} = {usd(implied_basic)}; "
        f"{price:g} x pre-round fully diluted {sh(pre_fd)} = {usd(implied_fd)}" if price else "not stated",
        "CONSISTENT (outstanding basis)" if pm and implied_basic and abs(pm[0] - implied_basic) / pm[0] < 0.01 else "MISMATCH",
        f"Stated deck pre-money {usd0(pm[0])} used for post-money; implied figures shown alongside." if pm else
        "Implied outstanding-basis figure used; labelled as such."))
    if pm and price:
        rv.add("M04", "MEDIUM", "Mismatch",
               f"Pre-money {usd0(pm[0])} matches price x outstanding shares, not fully diluted"
               if len(pm) == 1 and abs(pm[0] - implied_basic) / pm[0] < 0.01 else "Pre-money differs from implied",
               f"Deck states {usd0(pm[0])} ({_locs(deck.pre_money)}); the cap table states no pre-money. "
               f"Pre-round shares = Before totals less all {sh(round_total)} Seed-3 shares (issued, committed and "
               f"plug). The deck figure is within {abs(pm[0] - implied_basic) / pm[0]:.2%} of the outstanding-basis "
               f"figure and {abs(pm[0] - implied_fd) / pm[0]:.1%} below the fully diluted one.",
               refs=[f.ref.location for f in deck.pre_money] + [cap.issue_price.ref.location],
               arithmetic=f"{price:g} x {sh(pre_basic)} = {usd(implied_basic)} (diff {usd(implied_basic - pm[0])}); "
                          f"{price:g} x {sh(pre_fd)} = {usd(implied_fd)} (diff {usd(implied_fd - pm[0])}); "
                          f"deck-implied price on outstanding basis {usd0(pm[0])} / {sh(pre_basic)} = "
                          f"${pm[0] / pre_basic:.5f}",
               resolution="Post-money on the stated basis = deck pre-money + modelled proceeds. The implied priced "
                          "valuations are shown too and never labelled fully diluted when based on outstanding shares.",
               priority=10)

    # 3 Issue price
    rv.comparisons.append(Comparison(
        "Issue price per share", _locs(deck.share_price) or "not stated in deck",
        f"{price:g} at {cap.issue_price.ref.location}" + (
            f"; {cap.extras['round_fd_formula']['divisor']:g} embedded in {cap.extras['round_fd_formula']['cell']}"
            if cap.extras.get("round_fd_formula") else "") if price else "not stated",
        "NOT IN DECK" if not deck.share_price else (
            "MATCH" if all(abs(f.value - price) < 1e-6 for f in deck.share_price) else "MISMATCH"),
        f"Cap-table issue price {price:g} ({cap.issue_price.ref.location}) is the default pricing source." if price else "Blocked"))

    # 5 Share counts
    opt = sum(r.shares.get("OPT", 0) for r in cap.rows)
    pool = sum(r.shares.get("POOL", 0) for r in cap.rows)
    rv.comparisons.append(Comparison(
        "Share counts, options/RSUs, pool, fully diluted total",
        _locs(deck.share_counts) or "No share counts, option/RSU awards, pool or fully diluted totals stated in deck",
        f"Outstanding {sh(rv.derived['basic_before'])} ({cap.source_total_basic.ref.location}); options/RSUs "
        f"{sh(opt)}; unissued pool {sh(pool)}; fully diluted {sh(rv.derived['fd_before'])} "
        f"({cap.source_total_fd.ref.location})",
        "NOT IN DECK" if not deck.share_counts else "SEE NOTES",
        "Cap table figures used."))

    if len(pm) > 1:
        rv.add("M05", "MEDIUM", "Mismatch", "Deck states more than one pre-money", _locs(deck.pre_money), priority=11)
    if not deck.share_price:
        rv.add("M06", "INFO", "Mismatch", "Deck states no price per share",
               "No price-per-share figure appears in any slide text, table or speaker notes.", priority=86)
    if deck.image_flags:
        rv.add("IMG", "INFO", "Extraction", "Slides whose figures may be embedded in images",
               " | ".join(deck.image_flags) + ". Text extraction cannot read these; verify manually.",
               refs=[f.split(":")[0] for f in deck.image_flags], priority=84)
    leads = sorted({l for l, _ in deck.lead_investor})
    if leads:
        rv.add("L01", "INFO", "Extraction", "Lead investor per deck",
               "; ".join(f"{l} ({r.location} \"{r.label}\")" for l, r in deck.lead_investor), priority=88)
