"""Read every cell of the source workbook: formula text and last cached result.

The file is opened read-only; nothing is written back to the source.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

import openpyxl

ERROR_VALUES = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!")


@dataclass
class Cell:
    sheet: str
    coord: str
    formula: Optional[str]      # "=..." when the cell holds a formula
    value: Any                  # cached value (for formulas) or the constant

    @property
    def is_formula(self) -> bool:
        return self.formula is not None


@dataclass
class WorkbookDump:
    path: str
    sheets: dict[str, str]                         # name -> visible/hidden/veryHidden
    cells: dict[tuple[str, str], Cell]
    defined_names: dict[str, str]                  # name -> "Sheet!$A$1"
    hidden_rows: dict[str, list[int]] = field(default_factory=dict)
    hidden_cols: dict[str, list[str]] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def get(self, sheet: str, coord: str) -> Optional[Cell]:
        return self.cells.get((sheet, coord))

    def value(self, sheet: str, coord: str) -> Any:
        c = self.get(sheet, coord)
        return None if c is None else c.value

    def sheet_cells(self, sheet: str) -> list[Cell]:
        return [c for (s, _), c in self.cells.items() if s == sheet]


def extract_workbook(path: str) -> WorkbookDump:
    wb_f = openpyxl.load_workbook(path, data_only=False)
    wb_v = openpyxl.load_workbook(path, data_only=True)
    cells: dict[tuple[str, str], Cell] = {}
    sheets, hidden_rows, hidden_cols = {}, {}, {}
    for ws in wb_f.worksheets:
        sheets[ws.title] = ws.sheet_state
        hidden_rows[ws.title] = [r for r, d in ws.row_dimensions.items() if d.hidden]
        hidden_cols[ws.title] = [c for c, d in ws.column_dimensions.items() if d.hidden]
        wv = wb_v[ws.title]
        for row in ws.iter_rows():
            for c in row:
                if c.value is None:
                    continue
                if isinstance(c.value, str) and c.value.startswith("="):
                    cells[(ws.title, c.coordinate)] = Cell(ws.title, c.coordinate, c.value,
                                                           wv[c.coordinate].value)
                else:
                    cells[(ws.title, c.coordinate)] = Cell(ws.title, c.coordinate, None, c.value)
    names = {n: d.attr_text for n, d in wb_f.defined_names.items()}
    # Sheet-scoped names
    for ws in wb_f.worksheets:
        for n, d in getattr(ws, "defined_names", {}).items():
            names[f"{ws.title}::{n}"] = d.attr_text
    return WorkbookDump(path, sheets, cells, names, hidden_rows, hidden_cols)
