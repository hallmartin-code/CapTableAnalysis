"""Turn raw extraction dumps into a normalized cap table and deck round terms.

The cap-table parser targets the Carta-style "Summary" + "Intermediate" export
layout (stakeholder rows, one column per security class, 1:1 conversion
columns, totals rows).  Anything it cannot map is left out of the model and
reported, never guessed.
"""
from __future__ import annotations

import re
from typing import Optional

from .extract_deck import DeckDump
from .extract_xlsx import WorkbookDump
from .models import CapTable, DeckTerms, Figure, HolderRow, ShareClass, SourceRef

ROUND_CLASS_RE = re.compile(r"seed[\s-]*3", re.I)
PLACEHOLDER_RE = re.compile(r"remaining|planned|unallocated|to be (issued|allocated)|open allocation|\btbd\b", re.I)
POOL_RE = re.compile(r"available for (issuance|grant)|unissued|unallocated pool", re.I)
OPTIONS_MEMO_RE = re.compile(r"^options and rsu", re.I)
CODE_RE = re.compile(r"\(([A-Z0-9]+)\)")
FRACTION_RE = re.compile(r"fraction(al)? share|round(ed)? (down|up) to the nearest (whole )?share", re.I)


class CapTableParseError(Exception):
    pass


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def _col_letter(coord: str) -> str:
    return re.match(r"[A-Z]+", coord).group(0)


def _row_num(coord: str) -> int:
    return int(re.search(r"\d+", coord).group(0))


# --------------------------------------------------------------------------------------
# Cap table
# --------------------------------------------------------------------------------------

def parse_cap_table(wb: WorkbookDump) -> CapTable:
    detail_sheet, header_row = _find_detail_header(wb)
    headers = {c.coord and _col_letter(c.coord): str(c.value).strip()
               for c in wb.sheet_cells(detail_sheet) if _row_num(c.coord) == header_row and c.value}
    name_col = next(k for k, v in headers.items() if v.lower() == "name")
    id_col = next((k for k, v in headers.items() if "stakeholder id" in v.lower()), None)
    out_col = next((k for k, v in headers.items() if v.lower().startswith("outstanding shares")), None)
    fd_col = next((k for k, v in headers.items() if v.lower().startswith("fully diluted shares")), None)

    classes: list[ShareClass] = []
    conv_cols: dict[str, str] = {}
    for col, h in sorted(headers.items(), key=lambda kv: (len(kv[0]), kv[0])):
        code = CODE_RE.search(h)
        low = h.lower()
        if "conversion ratio" in low and code:
            conv_cols[code.group(1)] = col
        elif "option" in low:
            classes.append(ShareClass("OPT", "Options & RSUs outstanding", "option", col))
        elif "warrant" in low and code:
            classes.append(ShareClass(code.group(1), h, "warrant", col))
        elif code and "preferred" in low:
            classes.append(ShareClass(code.group(1), h, "preferred", col))
        elif code and "common" in low:
            classes.append(ShareClass(code.group(1), h, "common", col))
    for c in classes:
        c.conversion_col = conv_cols.get(c.key, "")
    opt_cls = next((c for c in classes if c.kind == "option"), None)
    classes.append(ShareClass("POOL", "Unissued option pool (available for issuance)", "pool",
                              opt_cls.source_col if opt_cls else ""))
    order = {"common": 0, "preferred": 1, "warrant": 2, "option": 3, "pool": 4}
    classes.sort(key=lambda c: order[c.kind])

    round_cls = next((c for c in classes if ROUND_CLASS_RE.search(c.name)), None)
    if round_cls is None:
        raise CapTableParseError("No Series Seed-3 share class found in the cap table headers.")

    # Locate label rows below the stakeholder block
    label_rows: dict[str, int] = {}
    for c in wb.sheet_cells(detail_sheet):
        if _col_letter(c.coord) == name_col and isinstance(c.value, str):
            low = c.value.strip().lower()
            for key in ("fully diluted shares", "total shares outstanding", "share class original issue price"):
                if low == key or low.startswith(key):
                    label_rows.setdefault(key, _row_num(c.coord))
    fd_row = label_rows.get("fully diluted shares")
    out_row = label_rows.get("total shares outstanding")
    price_row = label_rows.get("share class original issue price")
    if fd_row is None:
        raise CapTableParseError(f"'Fully diluted shares' totals row not found on sheet {detail_sheet}.")

    rows: list[HolderRow] = []
    memo_rows: list[tuple[int, str, float]] = []
    for r in range(header_row + 1, fd_row):
        name = wb.value(detail_sheet, f"{name_col}{r}")
        if name in (None, ""):
            continue
        name = str(name).strip()
        sid = str(wb.value(detail_sheet, f"{id_col}{r}") or "") if id_col else ""
        shares: dict[str, float] = {}
        for c in classes:
            if c.kind == "pool":
                continue
            col = c.conversion_col or c.source_col
            raw = _num(wb.value(detail_sheet, f"{c.source_col}{r}"))
            conv = _num(wb.value(detail_sheet, f"{col}{r}"))
            shares[c.key] = conv if c.conversion_col else raw
        if POOL_RE.search(name):
            pool = shares.pop("OPT", 0.0)
            rows.append(HolderRow(name, r, "pool", {"POOL": pool}, sid))
            continue
        if OPTIONS_MEMO_RE.search(name) and out_col and fd_col \
                and wb.value(detail_sheet, f"{out_col}{r}") in (None, "") \
                and wb.value(detail_sheet, f"{fd_col}{r}") in (None, ""):
            memo_rows.append((r, name, shares.get("OPT", 0.0)))
            continue
        nonzero = {k for k, v in shares.items() if v}
        if PLACEHOLDER_RE.search(name):
            rtype = "placeholder"
        elif not sid and nonzero == {round_cls.key}:
            rtype = "commitment"
        elif not sid:
            rtype = "aggregate"
        else:
            rtype = "holder"
        rows.append(HolderRow(name, r, rtype, shares, sid))

    f = wb.name

    def fig(sheet, coord, label=""):
        v = wb.value(sheet, coord)
        if not isinstance(v, (int, float)):
            return None
        return Figure(float(v), SourceRef(f, f"{sheet}!{coord}", label))

    cap = CapTable(file=f, company=_company_name(wb, detail_sheet), as_of=_as_of(wb, detail_sheet),
                   classes=classes, rows=rows, round_class=round_cls.key)
    cap.extras["detail_sheet"] = detail_sheet
    cap.extras["header_row"] = header_row
    cap.extras["memo_rows"] = memo_rows
    cap.extras["label_rows"] = label_rows
    cap.extras["cols"] = {"name": name_col, "id": id_col, "out": out_col, "fd": fd_col}

    if out_col and out_row:
        cap.source_total_basic = fig(detail_sheet, f"{out_col}{out_row}", "Total Shares outstanding")
    if fd_col:
        cap.source_total_fd = fig(detail_sheet, f"{fd_col}{fd_row}", "Fully diluted shares")

    # Per-class source totals (Intermediate FD row, outstanding row)
    for c in classes:
        figs = []
        if c.kind in ("pool",):
            continue
        if c.kind == "option":
            v = fig(detail_sheet, f"{c.source_col}{fd_row}", "Fully diluted shares (options + pool)")
            if v:
                cap.source_class_totals.setdefault("OPT+POOL", []).append(v)
            continue
        col = c.conversion_col or c.source_col
        v = fig(detail_sheet, f"{col}{fd_row}", "Fully diluted shares")
        if v:
            figs.append(v)
        if out_row:
            v = fig(detail_sheet, f"{c.source_col}{out_row}", "Total Shares outstanding")
            if v:
                figs.append(v)
        cap.source_class_totals[c.key] = figs

    # Issue prices
    if price_row:
        for c in classes:
            if c.kind != "preferred":
                continue
            p = fig(detail_sheet, f"{c.source_col}{price_row}", "Share Class Original Issue Price")
            if p:
                cap.issue_prices[c.key] = p
            if c.conversion_col:
                p2 = fig(detail_sheet, f"{c.conversion_col}{price_row}", "Share Class Original Issue Price")
                if p2:
                    cap.extras.setdefault("issue_price_alt", {})[c.key] = p2
        cap.issue_price = cap.issue_prices.get(round_cls.key)

    _parse_summary_sheet(wb, cap)
    _parse_round_cash(wb, cap)

    # Stated fractional-share convention anywhere in the workbook?
    for c in wb.cells.values():
        if isinstance(c.value, str) and FRACTION_RE.search(c.value):
            cap.fractional_convention = f"{c.sheet}!{c.coord}: {c.value[:120]}"
            break
    return cap


def _find_detail_header(wb: WorkbookDump) -> tuple[str, int]:
    for (sheet, coord), c in wb.cells.items():
        if isinstance(c.value, str) and c.value.strip().lower() == "stakeholder id":
            return sheet, _row_num(coord)
    raise CapTableParseError("Could not find a stakeholder-level sheet (header 'Stakeholder ID').")


def _company_name(wb: WorkbookDump, sheet: str) -> str:
    for c in wb.sheet_cells(sheet):
        if isinstance(c.value, str) and "cap table" in c.value.lower():
            return re.split(r"\s+(intermediate|summary|detailed)?\s*cap table", c.value, flags=re.I)[0].strip()
    return "Company (name not found in cap table)"


def _as_of(wb: WorkbookDump, sheet: str) -> str:
    for c in wb.sheet_cells(sheet):
        if isinstance(c.value, str):
            m = re.search(r"as of\s+([\d/.-]+)", c.value, re.I)
            if m:
                return m.group(1)
    return ""


def _parse_summary_sheet(wb: WorkbookDump, cap: CapTable) -> None:
    summ = next((s for s in wb.sheets if s != cap.extras["detail_sheet"] and "summary" in s.lower()), None)
    if not summ:
        return
    cap.extras["summary_sheet"] = summ
    cells = wb.sheet_cells(summ)
    hdr = {}
    for c in cells:
        if isinstance(c.value, str):
            low = c.value.lower().replace("\n", " ")
            if low.startswith("shares issued"):
                hdr["issued"] = (_col_letter(c.coord), _row_num(c.coord))
            elif low.startswith("fully diluted shares"):
                hdr["fd"] = (_col_letter(c.coord), _row_num(c.coord))
            elif low.startswith("cash raised"):
                hdr["cash"] = (_col_letter(c.coord), _row_num(c.coord))
            elif low.startswith("shares authorized"):
                hdr["auth"] = (_col_letter(c.coord), _row_num(c.coord))
    cap.extras["summary_cols"] = {k: v[0] for k, v in hdr.items()}
    fd_c = hdr.get("fd", ("D", 0))[0]
    cash_c = hdr.get("cash", ("F", 0))[0]
    summary_rows = {}
    for c in cells:
        if _col_letter(c.coord) != "A" or not isinstance(c.value, str):
            continue
        r = _row_num(c.coord)
        label = c.value.strip()
        summary_rows[label] = r
        code = CODE_RE.search(label)
        low = label.lower()
        v = wb.value(summ, f"{fd_c}{r}")
        ref = SourceRef(wb.name, f"{summ}!{fd_c}{r}", label)
        if code and not low.startswith("total") and isinstance(v, (int, float)):
            key = code.group(1)
            if key in {k.key for k in cap.classes}:
                cap.source_class_totals.setdefault(key, []).append(Figure(float(v), ref))
        elif low.startswith("options and rsus issued") and isinstance(v, (int, float)):
            cap.source_class_totals.setdefault("OPT", []).append(Figure(float(v), ref))
        elif POOL_RE.search(low) and isinstance(v, (int, float)):
            cap.source_class_totals.setdefault("POOL", []).append(Figure(float(v), ref))
        elif low == "totals" and isinstance(v, (int, float)):
            cap.source_total_fd_alt = Figure(float(v), ref)
        # Convertibles: rows with cash but no share columns
        cash = wb.value(summ, f"{cash_c}{r}")
        if (("safe" in low or "convertible" in low or "note" in low) and not low.startswith("total")
                and isinstance(cash, (int, float)) and wb.value(summ, f"{fd_c}{r}") is None):
            cap.convertibles.append(Figure(float(cash), SourceRef(wb.name, f"{summ}!{cash_c}{r}", label)))
    cap.extras["summary_rows"] = summary_rows


def _terms(formula: str) -> list[float]:
    return [float(x) for x in re.findall(r"(?<![A-Z$])(\d+(?:\.\d+)?)", formula)]


def _parse_round_cash(wb: WorkbookDump, cap: CapTable) -> None:
    """Split the Seed-3 cash and share formulas on the Summary sheet into components."""
    summ = cap.extras.get("summary_sheet")
    if not summ:
        return
    rcls = cap.cls(cap.round_class)
    row = next((r for lab, r in cap.extras["summary_rows"].items()
                if f"({rcls.key})" in lab and not lab.lower().startswith("total")), None)
    if row is None:
        return
    cols = cap.extras["summary_cols"]
    fd_cell = wb.get(summ, f"{cols.get('fd', 'D')}{row}")
    cash_cell = wb.get(summ, f"{cols.get('cash', 'F')}{row}")
    cap.extras["round_summary_row"] = row
    price = cap.issue_price.value if cap.issue_price else None

    commit_rows = cap.rows_of("commitment")
    commit_cash = [(r, r.shares[cap.round_class] * price) for r in commit_rows] if price else []
    cap.extras["commitment_cash"] = commit_cash

    if cash_cell is not None and isinstance(cash_cell.value, (int, float)):
        cap.round_cash_total = Figure(float(cash_cell.value),
                                      SourceRef(wb.name, f"{summ}!{cash_cell.coord}", "Cash Raised (USD)"))
    if fd_cell is not None and fd_cell.formula:
        m = re.match(r"=\s*(\d+(?:\.\d+)?)\s*\+\s*\(([\d.+\s]+)\)\s*/\s*(\d+(?:\.\d+)?)\s*$", fd_cell.formula)
        if m:
            cap.extras["round_fd_formula"] = {
                "cell": f"{summ}!{fd_cell.coord}", "formula": fd_cell.formula,
                "existing_shares": float(m.group(1)),
                "cash_terms": [float(x) for x in m.group(2).split("+")],
                "divisor": float(m.group(3)),
            }
    if cash_cell is not None and cash_cell.formula and price:
        terms = _terms(cash_cell.formula)
        cap.extras["round_cash_terms"] = terms
        remaining = list(terms)
        matched = 0.0
        for _, amt in commit_cash:
            hit = next((t for t in remaining if abs(t - amt) <= 1.0), None)
            if hit is not None:
                remaining.remove(hit)
                matched += hit
        loc = f"{summ}!{cash_cell.coord}"
        if commit_cash and matched:
            cap.round_cash_commitments = Figure(matched, SourceRef(
                wb.name, loc, "formula terms matching commitment rows at the issue price"))
        fdf = cap.extras.get("round_fd_formula")
        if fdf:
            open_amt = sum(fdf["cash_terms"]) - matched
            hit = next((t for t in remaining if abs(t - open_amt) <= 1.0), None)
            if hit is not None:
                remaining.remove(hit)
                cap.round_cash_open = Figure(hit, SourceRef(
                    wb.name, loc, "formula term for the unsold 'Remaining Round Planned' allocation"))
        if len(remaining) == 1:
            cap.round_cash_existing = Figure(remaining[0], SourceRef(
                wb.name, loc, "formula term for Seed-3 already issued"))


# --------------------------------------------------------------------------------------
# Deck
# --------------------------------------------------------------------------------------

MONEY = r"\$\s?(\d+(?:[.,]\d+)*)\s?(B|M|MM|K|k|m|b|million|thousand|billion)?\b"
TABLE_LABELS = [
    ("pre_money", re.compile(r"pre[\s-]*money", re.I)),
    ("round_size", re.compile(r"capital goal|round size|raise amount|target raise|total raise|raising", re.I)),
    ("committed", re.compile(r"closed|committed|soft[\s-]*circled", re.I)),
    ("open_allocation", re.compile(r"open to new|remaining|still available|open allocation", re.I)),
    ("share_price", re.compile(r"price per share|share price|issue price", re.I)),
]
TEXT_PATTERNS = [
    ("pre_money", re.compile(MONEY + r"\s+pre(?:[\s-]*money)?\b", re.I)),
    ("pre_money", re.compile(r"pre[\s-]*money(?: valuation)?(?: of| at|:)?\s+" + MONEY, re.I)),
    ("round_size", re.compile(r"raising\s+" + MONEY, re.I)),
    ("committed", re.compile(MONEY + r"\s+(?:closed|committed)", re.I)),
    ("share_price", re.compile(r"(?:price per share|per share price|share price)\D{0,15}\$\s?(\d+\.\d+)()", re.I)),
    ("share_counts", re.compile(r"(\d{1,3}(?:,\d{3}){2,})()\s+(?:fully[\s-]diluted|shares)", re.I)),
]


def parse_money(num: str, unit: Optional[str]) -> float:
    v = float(num.replace(",", ""))
    u = (unit or "").lower()
    if u in ("m", "mm", "million"):
        v *= 1e6
    elif u in ("k", "thousand"):
        v *= 1e3
    elif u in ("b", "billion"):
        v *= 1e9
    return v


def parse_deck_terms(deck: DeckDump) -> DeckTerms:
    t = DeckTerms(deck.name, slide_count=len(deck.slides))
    seen = set()

    def add(metric, value, loc, label):
        key = (metric, round(value, 4), loc, label)
        if key in seen:
            return
        seen.add(key)
        getattr(t, metric).append(Figure(value, SourceRef(deck.name, loc, label)))

    for s in deck.slides:
        for b in s.blocks:
            loc = f"{deck.unit} {s.index}" + (" speaker notes" if b.kind == "notes" else "")
            if b.kind == "table_row" and "||" in b.text:
                cells = [c.strip() for c in b.text.split("||")]
                label, rest = cells[0], " ".join(cells[1:])
                if re.search(r"lead investor", label, re.I) and rest:
                    t.lead_investor.append((rest, SourceRef(deck.name, loc, f"{label}: {rest}")))
                m = re.search(MONEY, rest)
                if m:
                    for metric, rx in TABLE_LABELS:
                        if rx.search(label):
                            add(metric, parse_money(m.group(1), m.group(2)), loc, f"{label}: {rest}")
                            break
                continue
            for metric, rx in TEXT_PATTERNS:
                for m in rx.finditer(b.text):
                    if metric == "share_price":
                        val = float(m.group(1))
                    elif metric == "share_counts":
                        val = float(m.group(1).replace(",", ""))
                    else:
                        val = parse_money(m.group(1), m.group(2))
                    add(metric, val, loc, _snippet(b.text, m.start(), m.end()))
            for m in re.finditer(r"(\w[\w ]{0,20}?)\s*[–-]\s*led", b.text):
                t.lead_investor.append((m.group(1).strip(), SourceRef(deck.name, loc, _snippet(b.text, m.start(), m.end()))))
        # Figures that may live only inside images
        if s.large_image_area >= 0.6 and s.text_chars < 150:
            t.image_flags.append(f"{deck.unit} {s.index}: a picture covers ~{s.large_image_area:.0%} of the slide and "
                                 f"there is little extractable text; any figures in it need manual verification")
        elif s.large_image_area >= 0.20:
            t.image_flags.append(f"{deck.unit} {s.index}: a large picture (~{s.large_image_area:.0%} of the slide) "
                                 f"may contain chart/table figures not extractable as text")
    return t


def _snippet(text: str, a: int, b: int, pad: int = 25) -> str:
    s = text[max(0, a - pad): b + pad].strip(" |")
    return ("…" if a > pad else "") + s + ("…" if b + pad < len(text) else "")
