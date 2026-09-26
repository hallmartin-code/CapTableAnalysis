"""One-page PDF investor ownership summary, rendered from templates/document_structure.py.

`build_content` / `build_blocked_content` map a calculation onto the template's field keys
(formatted strings and table rows).  `render` lays the page out section by section in the
template's order, using its headings, labels, columns, sentence patterns and fixed text.
The blank specimen in templates/ is produced by this same `render` with placeholder values.
"""
from __future__ import annotations

import os
import re
from datetime import date
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from templates import document_structure as T

from .calc import Result
from .fmt import pct, pp, sh, usd, usd0
from .models import CapTable, DeckTerms, Inputs, Issue

C = {k: colors.HexColor(v["hex"]) for k, v in T.COLOR_ROLES.items()}
FONT, BOLD = "Helvetica", "Helvetica-Bold"
TY = T.TYPOGRAPHY
NO_ISSUES = "No material data issues found."


# ------------------------------------------------------------------------------------ content

def round_labels(cap: CapTable) -> tuple[str, str]:
    """('Series X', 'Series X Preferred') from the round class name, without the class code."""
    full = re.sub(r"\s*\([A-Z0-9]+\)\s*$", "", cap.cls(cap.round_class).name).strip()
    return re.sub(r"\s+Preferred.*$", "", full).strip(), full


def _header(cap: CapTable, inp: Inputs) -> dict:
    short, full = round_labels(cap)
    return {"company": cap.company, "round_label": short, "round_class_name": full, "investor": inp.investor,
            "cap_table_as_of": cap.as_of or "date not stated", "prepared_date": f"{date.today():%B %d, %Y}"}


def _issues(top: list[Issue]) -> list[dict]:
    return [{"title": i.title, "severity": i.severity, "evidence": (i.arithmetic or i.detail)[:330],
             "sources": "; ".join(i.refs[:4])} for i in top]


def _inputs(inp: Inputs) -> list[dict]:
    def v(x):
        if isinstance(x, float):
            return f"{x:,.4f}" if x < 10 else f"{x:,.2f}"
        return str(x)
    return [{"name": x.name, "value": v(x.value), "source": x.source} for x in inp.resolved]


def build_content(cap: CapTable, inp: Inputs, res: Result, top: list[Issue]) -> dict:
    v = res.valuation
    iv = res.investor_row
    c = _header(cap, inp)
    parts = [("issued cash", v["proceeds_existing"]), ("commitment rows", v["proceeds_commitments_in_before"]),
             ("commitments not in cap table", v["proceeds_uncounted"]), ("kept plug row", v["proceeds_open_kept"]),
             ("this check", v["proceeds_new"])]
    ph = [r for r in res.rows if r.row_type == "placeholder" and r.adj_placeholder]
    bridge = [f"{lbl[0].lower() + lbl[1:]} {usd0(val)}" for lbl, val in res.post_bridge if abs(val) >= 0.5]
    c.update({
        "check_size": usd0(inp.check_size), "new_shares": sh(res.new_shares),
        "basic_ownership": pct(iv.pct_after_basic, 3), "fd_ownership": pct(iv.pct_after_fd, 3),
        "post_money": usd0(v["post_money"]),
        "check_size_exact": usd(inp.check_size), "share_price": f"${inp.share_price:g}",
        "new_shares_exact": sh(res.new_shares, 4),
        "fraction_note": (f"stated convention: {cap.fractional_convention}" if cap.fractional_convention else
                          "no fractional-share convention is stated, so the issued count needs confirmation"),
        "after_basic_shares": sh(res.totals["after_basic"]), "after_fd_shares": sh(res.totals["after_fd"]),
        "pre_money": usd0(v["pre_money"]),
        "pre_money_source": next((x.source for x in inp.resolved if x.name == "Pre-money valuation"), "not stated"),
        "proceeds": usd0(v["proceeds"]),
        "proceeds_breakdown": " + ".join(f"{n} {usd0(a)}" for n, a in parts if a or n == "this check"),
        "implied_pre_basic": usd0(v["implied_pre_basic"]), "implied_pre_fd": usd0(v["implied_pre_fd"]),
        "implied_post_basic": usd0(v["implied_post_basic"]), "implied_post_fd": usd0(v["implied_post_fd"]),
        "post_gap": usd0(v["post_diff_basic"]),
        "bridge_items": "; ".join(bridge) or "no difference",
        "tie_out_statuses": "; ".join(f"{n}: {'OK' if ok else 'FAIL'}" for n, ok, _ in res.checks[:3]),
        "plug_clause": (f" and removes the unsold plug row '{ph[0].name}' ({sh(-ph[0].adj_placeholder)} sh) "
                        "through a separate adjustment") if ph else "",
        "commitments_clause": ("Commitments already in the pro forma are not added again."
                               if inp.commitments_in_before else
                               "Commitments not in the cap table are added as one aggregate row."),
        "class_rows": [[cr.name.replace(" Preferred", " Pref.").replace(" Stock", ""), sh(cr.before, 0),
                        pct(cr.pct_before_basic) if cr.pct_before_basic is not None else "excl.",
                        pct(cr.pct_before_fd), sh(cr.after, 0),
                        pct(cr.pct_after_basic) if cr.pct_after_basic is not None else "excl.",
                        pct(cr.pct_after_fd), pp(cr.pct_after_fd - cr.pct_before_fd, 3)] for cr in res.classes],
        "total_row": ["Total", sh(res.totals["before_fd"], 0), "100.00%", "100.00%", sh(res.totals["after_fd"], 0),
                      "100.00%", "100.00%", ""],
        "investor_row": [f"of which {inp.investor} ({c['round_label']})", "-", "-", "-", sh(iv.after_fd, 0),
                         pct(iv.pct_after_basic), pct(iv.pct_after_fd), pp(iv.delta_fd, 3)],
        "top_issues": _issues(top),
        "resolved_inputs": _inputs(inp),
    })
    return c


def build_blocked_content(cap: CapTable, inp: Inputs, top: list[Issue], derived: dict) -> dict:
    c = _header(cap, inp)
    ties = bool(cap.source_total_basic and cap.source_total_fd
                and abs(derived.get("basic_before", 0) - cap.source_total_basic.value) <= 0.01
                and abs(derived.get("fd_before", 0) - cap.source_total_fd.value) <= 0.01)
    c.update({
        "missing": list(inp.missing),
        "resolved_inputs": _inputs(inp),
        "top_issues": _issues(top),
        "source_outstanding": sh(derived.get("basic_before")),
        "source_outstanding_ref": cap.source_total_basic.ref.location if cap.source_total_basic else "not found",
        "source_fd": sh(derived.get("fd_before")),
        "source_fd_ref": cap.source_total_fd.ref.location if cap.source_total_fd else "not found",
        "tie_statement": "both tie to independent sums" if ties else "differences are itemised in the workbook",
    })
    return c


# ------------------------------------------------------------------------------------ rendering

def _styles(k: float) -> dict:
    kv = min(k, 1.0) / k          # metric values never grow above their base size

    def ps(name, size, font=FONT, color="body", lead=1.25, **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size * k, leading=size * k * lead,
                              textColor=C[color], **kw)
    return {
        "title": ps("title", TY["title_pt"], BOLD, "ink", 1.1),
        "sub": ps("sub", TY["subtitle_pt"], color="muted"),
        "h": ps("h", TY["section_heading_pt"], BOLD, "ink", spaceBefore=5 * k, spaceAfter=2 * k),
        "body": ps("body", TY["body_pt"]),
        "small": ps("small", TY["small_pt"]),
        "notes": ps("notes", TY["notes_pt"], color="muted"),
        "statlab": ps("statlab", TY["metric_label_pt"], BOLD, "ink", alignment=TA_CENTER),
        "stat": ps("stat", TY["metric_value_pt"] * kv, BOLD, "ink", 1.1, alignment=TA_CENTER),
        "hero": ps("hero", TY["hero_value_pt"] * kv, BOLD, "coral", 1.1, alignment=TA_CENTER),
        "cell": ps("cell", TY["table_pt"]),
        "banner": ps("banner", TY["blocked_banner_pt"], BOLD, "coral", 1.1),
    }


def _grid(data, widths, k, bold_rows=(), highlight_rows=(), left_cols=(0,)):
    t = Table(data, colWidths=widths, repeatRows=1)
    st = [("FONT", (0, 0), (-1, -1), FONT, TY["table_pt"] * k), ("TEXTCOLOR", (0, 0), (-1, -1), C["body"]),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, C["rule"]),
          ("TOPPADDING", (0, 0), (-1, -1), 1.6 * k), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6 * k),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
          ("BACKGROUND", (0, 0), (-1, 0), C["gray_bg"]), ("FONT", (0, 0), (-1, 0), BOLD, (TY["table_pt"] - 0.2) * k),
          ("TEXTCOLOR", (0, 0), (-1, 0), C["ink"])]
    st += [("ALIGN", (c, 0), (c, -1), "LEFT") for c in left_cols]
    for r in bold_rows:
        st += [("FONT", (0, r), (-1, r), BOLD, TY["table_pt"] * k), ("TEXTCOLOR", (0, r), (-1, r), C["ink"])]
    for r in highlight_rows:
        st += [("BACKGROUND", (0, r), (-1, r), C["cream"]), ("FONT", (0, r), (-1, r), BOLD, TY["table_pt"] * k),
               ("TEXTCOLOR", (0, r), (-1, r), C["ink"])]
    t.setStyle(TableStyle(st))
    return t


def _esc(values: dict) -> dict:
    return {k: escape(v) if isinstance(v, str) else v for k, v in values.items()}


def _check_required(variant: str, content: dict) -> None:
    list_sections = ("top_issues", "sources_assumptions", "resolved_inputs", "class_table", "required_inputs")
    missing = [f.key for s in T.SECTIONS[variant] for f in s.fields
               if f.required and s.id not in list_sections and f.key not in content]
    needed = {"calculated": ("class_rows", "total_row", "investor_row", "top_issues", "resolved_inputs"),
              "blocked": ("missing", "top_issues", "resolved_inputs")}[variant]
    missing += [k for k in needed if k not in content]
    if variant == "blocked" and not content.get("missing"):
        missing.append("missing (the blocked variant needs at least one required input)")
    if missing:
        raise KeyError(f"Report content is missing required template fields: {', '.join(sorted(set(missing)))}")


def _story(variant: str, content: dict, k: float, width: float) -> list:
    st = _styles(k)
    e = _esc({key: v for key, v in content.items() if isinstance(v, str)})
    out: list = []
    for s in T.SECTIONS[variant]:
        if s.heading:
            out.append(Paragraph(escape(s.heading), st["h"]))
        if s.id == "header":
            title, sub = T.fill(s.pattern, e).split("\n")
            sub = sub.replace(e["investor"], f"<b>{e['investor']}</b>", 1).replace(" | ", " &nbsp;|&nbsp; ")
            out += [Paragraph(title, st["title"]), Paragraph(sub, st["sub"]), Spacer(1, 6 * k)]
        elif s.id == "key_metrics":
            labels = [Paragraph(escape(f.label.format(**content)), st["statlab"]) for f in s.fields]
            vals = [Paragraph(e[f.key], st["hero" if f.key == "basic_ownership" else "stat"]) for f in s.fields]
            t = Table([labels, vals], colWidths=[width / len(s.fields)] * len(s.fields))
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C["cream"]),
                                   ("BOX", (0, 0), (-1, -1), 0.5, C["rule"]),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4 * k),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * k)]))
            out += [t, Spacer(1, 3 * k)]
        elif s.id == "valuation":
            text = T.fill(s.pattern, e)
            out.append(Paragraph(text.replace(e["post_money"], f"<b>{e['post_money']}</b>", 1), st[s.style]))
        elif s.id == "class_table":
            rows = [list(s.columns)] + content["class_rows"] + [content["total_row"], content["investor_row"]]
            cws = [width * x for x in (0.285, 0.11, 0.09, 0.085, 0.11, 0.09, 0.085, 0.145)]
            out += [_grid(rows, cws, k, bold_rows=[len(rows) - 2], highlight_rows=[len(rows) - 1]),
                    Spacer(1, 2 * k)]
        elif s.id == "top_issues":
            items = content["top_issues"]
            if not items:
                out.append(Paragraph(NO_ISSUES, st["small"]))
            for n, it in enumerate(items, 1):
                v = _esc(it)
                v.update(n=n, title=f"<b>{v['title']}</b>", sources=f"<font color='#7A7A7A'>{v['sources']}</font>")
                out += [Paragraph(T.fill(s.pattern, v), st["small"]), Spacer(1, 1.5 * k)]
        elif s.id == "sources_assumptions":
            parts = []
            for it in content["resolved_inputs"]:
                v = _esc(it)
                v["name"] = f"<b>{v['name']}</b>"
                parts.append(T.fill(s.pattern, v))
            fixed = escape(s.fixed_text).replace("Treatment:", "<b>Treatment:</b>", 1)
            out += [Paragraph(" &nbsp;&bull;&nbsp; ".join(parts + [fixed]), st["notes"]), Spacer(1, 4 * k)]
        elif s.id == "disclaimer":
            out.append(Paragraph(escape(s.fixed_text), st["notes"]))
        elif s.id == "status_banner":
            banner, expl = s.fixed_text.split("\n", 1)
            out += [Spacer(1, 4 * k), Paragraph(escape(banner), st["banner"]), Spacer(1, 4 * k),
                    Paragraph(escape(expl), st["body"])]
        elif s.id == "required_inputs":
            for n, m in enumerate(content["missing"], 1):
                out += [Paragraph(T.fill(s.pattern, {"n": f"<b>{n}</b>", "missing": escape(m)}),
                                  st["body"]), Spacer(1, 2 * k)]
        elif s.id == "resolved_inputs":
            rows = [list(s.columns)] + [[it["name"], it["value"], Paragraph(escape(it["source"]), st["cell"])]
                                        for it in content["resolved_inputs"]]
            out.append(_grid(rows, [width * 0.2, width * 0.14, width * 0.66], k, left_cols=(0, 2)))
        elif s.pattern:
            out.append(Paragraph(T.fill(s.pattern, e), st[s.style]))
            if s.id == "source_facts":
                out.append(Spacer(1, 6 * k))
    return out


def _footer(title: str, logo: Optional[str], compiled: str):
    def draw(canvas, doc):
        canvas.saveState()
        w = letter[0]
        texts = [f" {title}", str(canvas.getPageNumber()),
                 f"Compiled on {compiled} by TEN Capital Network"]
        canvas.setFont(FONT, TY["footer_pt"])
        gap, lw, lh = 22, 0.67 * inch, 0.25 * inch
        widths = [canvas.stringWidth(t, FONT, TY["footer_pt"]) for t in texts]
        x = (w - (sum(widths) + 3 * gap + (lw if logo else 0))) / 2
        y = 0.42 * inch
        canvas.setFillColor(C["muted"])
        for t, tw in zip(texts, widths):
            canvas.drawString(x, y, t)
            x += tw + gap
        if logo:
            canvas.drawImage(logo, x, y - 0.08 * inch, lw, lh, mask="auto", preserveAspectRatio=True)
        canvas.setStrokeColor(C["rule"])
        canvas.setLineWidth(0.5)
        canvas.line(0.6 * inch, 0.72 * inch, w - 0.6 * inch, 0.72 * inch)
        canvas.restoreState()
    return draw


def render(path: str, variant: str, content: dict, logo: Optional[str] = None,
           compiled: Optional[str] = None) -> float:
    """Render one page from template + content; returns the fit scale used."""
    compiled = compiled or f"{date.today():%B %d, %Y}"
    import pymupdf
    _check_required(variant, content)
    base = T.DOCUMENT_TITLE if variant == "calculated" else T.BLOCKED_TITLE
    title = f"{content['company']} {content['round_label']} {base}"
    m = T.PAGE["margins_in"]
    width = letter[0] - (m["left"] + m["right"]) * inch
    for k in T.FIT_SCALES:
        doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=m["left"] * inch, rightMargin=m["right"] * inch,
                                topMargin=m["top"] * inch, bottomMargin=m["bottom"] * inch, title=title,
                                author="TEN Capital Network")
        foot = _footer(title, logo, compiled)
        doc.build(_story(variant, content, k, width), onFirstPage=foot, onLaterPages=foot)
        with pymupdf.open(path) as d:
            if d.page_count == T.PAGE["pages"]:
                return k
    raise RuntimeError("Report does not fit on one page even at the smallest fit scale.")


def write_pdf(path: str, cap: CapTable, deck: DeckTerms, inp: Inputs, res: Result, top_issues: list[Issue],
              logo: Optional[str] = None) -> float:
    return render(path, "calculated", build_content(cap, inp, res, top_issues), logo)


def write_blocked_pdf(path: str, cap: CapTable, deck: DeckTerms, inp: Inputs, top_issues: list[Issue],
                      derived: dict, logo: Optional[str] = None) -> float:
    return render(path, "blocked", build_blocked_content(cap, inp, top_issues, derived), logo)


def default_logo() -> Optional[str]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(here, "assets", "TEN_Capital_logo_footer.png"),
              os.path.join(os.path.dirname(here), "TEN_Capital_logo_footer.png")):
        if os.path.exists(p):
            return p
    return None
