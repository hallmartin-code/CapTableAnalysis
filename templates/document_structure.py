"""Canonical structure of the one-page Investor Ownership Summary.

Single source of truth for the report's shape: the two variants (calculated and
blocked), which sections exist and in what order, each section's heading, the
fields it carries, their format, where each value comes from, whether it is
required, what is shown when a value is absent, the sentence patterns the fields
are poured into, and the page rules that keep the report on exactly one page.

It contains no company data.  It describes the container, not any instance of it.

Consumers:

* ``captable_app/pdf_report.py`` takes headings, labels, table columns, text
  patterns, fixed text and fit scales from here, and refuses to render content
  that is missing a required field.
* ``templates/generate_template.py`` renders blank specimen PDFs through the real
  renderer and writes the Markdown and JSON versions of this template.

Change the report's structure here first, then run
``python -m templates.generate_template`` to refresh the template artifacts.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional

TEMPLATE_VERSION = "1.0"
DOCUMENT_TITLE = "Investor Ownership Summary"
BLOCKED_TITLE = "Ownership - Unable to Calculate"

# ---------------------------------------------------------------------------------------
# Page, typography, colour, footer
# ---------------------------------------------------------------------------------------
PAGE = {
    "size": "US Letter",
    "orientation": "portrait",
    "width_pt": 612,
    "height_pt": 792,
    "margins_in": {"left": 0.6, "right": 0.6, "top": 0.5, "bottom": 0.85},
    "pages": 1,
    "overflow_rule": ("Render, count pages, and step down through FIT_SCALES until the report is exactly one "
                      "page. If the smallest scale still overflows, fail instead of saving."),
}

FIT_SCALES = (1.1, 1.05, 1.0, 0.96, 0.92, 0.88, 0.84, 0.8, 0.76)

TYPOGRAPHY = {
    "family": "Helvetica / Helvetica-Bold (Inter or Open Sans when embedded)",
    "title_pt": 17, "subtitle_pt": 9, "section_heading_pt": 10.5, "body_pt": 8.3, "small_pt": 7.4,
    "notes_pt": 6.2, "table_pt": 7.3, "metric_label_pt": 7.4, "metric_value_pt": 15, "hero_value_pt": 17,
    "blocked_banner_pt": 22, "footer_pt": 7,
    "scaling": "All sizes except the footer are multiplied by the active fit scale; metric values never scale above 1.0",
    "minimum_readable_pt": 6.5,
}

COLOR_ROLES = {
    "ink": {"hex": "#000000", "role": "Title, headings, metric values, bold table rows"},
    "body": {"hex": "#4B4F58", "role": "Body copy and table cells"},
    "muted": {"hex": "#7A7A7A", "role": "Subtitle, source locations, notes, disclaimer, footer text"},
    "coral": {"hex": "#ED5644", "role": "Hero metric (basic ownership) and the 'Unable to calculate' banner only"},
    "rule": {"hex": "#CBD6E2", "role": "Table row dividers, metric box border, footer rule"},
    "gray_bg": {"hex": "#F7F7F7", "role": "Table header fill"},
    "cream": {"hex": "#FFFDF6", "role": "Metric strip background; new-investor table row"},
}

FOOTER = {
    "pattern": "[Document title]   [Page #]   Compiled on [Month DD, YYYY] by TEN Capital Network   [TEN Capital logo]",
    "document_title": "[Company name] [Round label] " + DOCUMENT_TITLE,
    "document_title_blocked": "[Company name] [Round label] " + BLOCKED_TITLE,
    "font": "7 pt, centred, muted",
    "logo": "assets/TEN_Capital_logo_footer.png at 0.67 x 0.25 in",
    "rule": "0.5 pt hairline above the footer",
}

# ---------------------------------------------------------------------------------------
# Field and section model
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    fmt: str                       # usd0, usd2, usd4, shares, shares4, pct3, pct2, pp3, date, text, list, table
    source: str                    # where the app takes the value from
    placeholder: str               # shown in the blank specimen
    required: bool = True
    empty: str = ""                # what is printed when an optional value is absent ("" = omit)
    max_chars: Optional[int] = None
    notes: str = ""


@dataclass(frozen=True)
class Section:
    id: str
    heading: str                   # "" = no printed heading
    purpose: str
    fields: tuple[Field, ...] = ()
    pattern: str = ""              # sentence pattern filled with {field_key}
    columns: tuple[str, ...] = ()  # for table sections
    rows: str = ""                 # row specification for table sections
    fixed_text: str = ""           # text that is always printed verbatim
    rules: tuple[str, ...] = ()
    style: str = "body"


VARIANTS = {
    "calculated": "All inputs resolved; ownership calculated.",
    "blocked": ("A required input is missing or conflicting. No ownership percentage, share count or valuation for "
                "the investor may appear anywhere on the page."),
}

# --- shared fields -------------------------------------------------------------------------------
F_COMPANY = Field("company", "Company", "text", "Cap table title cell (text before 'Cap Table')", "[Company name]")
F_ROUND = Field("round_label", "Round", "text", "Name of the round share class in the cap table header, "
                "without the 'Preferred (code)' suffix", "[Round label]")
F_ROUND_CLASS = Field("round_class_name", "Round security", "text", "Full round share-class name from the cap table",
                      "[Round share class]")
F_INVESTOR = Field("investor", "Investor", "text", "--investor (default 'New investor')", "[Investor name]", max_chars=60)
F_ASOF = Field("cap_table_as_of", "Cap table as of", "date", "Cap table 'As of' line", "[M/D/YYYY]",
               required=False, empty="date not stated")
F_PREPARED = Field("prepared_date", "Prepared", "date", "Run date", "[Month DD, YYYY]")

ISSUE_FIELDS = (
    Field("title", "Finding", "text", "validate.Issue.title (generated from the values found)", "[Finding title]",
          max_chars=110),
    Field("severity", "Severity", "text", "HIGH / MEDIUM / LOW", "HIGH|MEDIUM|LOW"),
    Field("evidence", "Evidence", "text", "Issue arithmetic, else detail", "[Both values and the arithmetic]",
          max_chars=330),
    Field("sources", "Source", "text", "Up to four exact locations (Sheet!Cell, Slide N)",
          "[Sheet!Cell; Slide N]"),
)
INPUT_FIELDS = (
    Field("name", "Input", "text", "resolve.ResolvedInput.name", "[Input name]"),
    Field("value", "Value", "text", "Resolved value", "[Value]"),
    Field("source", "Source", "text", "Workbook, tab and cell, deck slide and quoted label, or CLI flag",
          "[File | Location \"quoted label\"]"),
)

TOP_ISSUES = Section(
    "top_issues", "Top 3 data issues",
    "The three most material source problems: severity first, then materiality priority. INFO items never appear.",
    fields=ISSUE_FIELDS,
    pattern="{n}. {title} [{severity}] - {evidence} Source: {sources}.",
    rules=("Exactly three items when three or more non-INFO issues exist; fewer otherwise.",
           "Empty state: 'No material data issues found.'"),
    style="small",
)

DISCLAIMER = Section(
    "disclaimer", "", "TEN standard disclaimer, required on investment-related documents.",
    fixed_text=("Disclaimer: TEN is a \"Funding as a Service\" program. It is not a registered broker-dealer and does "
                "not offer investment advice or advise on the raising of capital through securities offerings. TEN "
                "does not recommend or otherwise suggest that any investor make an investment in a specific company, "
                "or that any company offer securities to a particular investor. TEN takes no part in the negotiation "
                "or execution of transactions for the purchase or sale of securities, and at no time has possession "
                "of funds or securities. No securities transactions are executed or negotiated on or through the TEN "
                "program. TEN receives no compensation in connection with the purchase or sale of securities."),
    style="notes",
)

# --- calculated variant ------------------------------------------------------------------------
CALCULATED: tuple[Section, ...] = (
    Section(
        "header", "", "Identifies company, round, investor and dates.",
        fields=(F_COMPANY, F_ROUND, F_INVESTOR, F_ROUND_CLASS, F_ASOF, F_PREPARED),
        pattern=("{company} - {round_label} investor ownership\n"
                 "Investor: {investor} | Round: {round_class_name} (priced) | Cap table as of {cap_table_as_of} | "
                 "Prepared {prepared_date}"),
        style="title",
    ),
    Section(
        "key_metrics", "", "Five headline figures in one strip; basic ownership is the single coral hero value.",
        fields=(
            Field("check_size", "Check size", "usd0", "--check-size, or the full open allocation when stated "
                  "unambiguously", "[$ amount]"),
            Field("new_shares", "New {round_label} shares", "shares", "check size / share price (unrounded)",
                  "[shares]"),
            Field("basic_ownership", "Basic ownership", "pct3", "Investor After shares / After issued and "
                  "outstanding shares", "[NN.NNN%]", notes="Hero value (coral)"),
            Field("fd_ownership", "Fully diluted ownership", "pct3", "Investor After shares / After fully "
                  "diluted shares", "[NN.NNN%]"),
            Field("post_money", "Post-money valuation", "usd0", "Priced pre-money + proceeds in the modelled "
                  "financing", "[$ amount]"),
        ),
        rules=("Labels on one line, values on the next, centred, five equal columns.",),
        style="metrics",
    ),
    Section(
        "share_math", "", "Shows how the new share count was derived and what each ownership basis contains.",
        fields=(
            Field("check_size_exact", "Check size", "usd2", "Resolved input", "[$X,XXX,XXX.XX]"),
            Field("share_price", "Share price", "usd4", "Cap-table round issue price, or --share-price",
                  "[$N.NNNN]"),
            Field("new_shares_exact", "New shares (4 dp)", "shares4", "check / price, unrounded",
                  "[N,NNN,NNN.NNNN]"),
            Field("fraction_note", "Fractional-share note", "text", "Stated convention, else the confirmation note",
                  "[fractional-share convention or confirmation note]"),
            Field("after_basic_shares", "After outstanding shares", "shares", "Sum of After basic column",
                  "[NN,NNN,NNN.NN]"),
            Field("after_fd_shares", "After fully diluted shares", "shares", "Sum of After FD column",
                  "[NN,NNN,NNN.NN]"),
        ),
        pattern=("New shares = {check_size_exact} / {share_price} = {new_shares_exact} (unrounded; {fraction_note}). "
                 "Basic = issued and outstanding common + preferred ({after_basic_shares} after); fully diluted adds "
                 "options/RSUs and the unissued pool ({after_fd_shares} after)."),
        style="small",
    ),
    Section(
        "valuation", "Post-money valuation and basis",
        "States the post-money, its components and source, the implied priced valuations on both share bases, and "
        "a bridge that explains every dollar of difference.",
        fields=(
            Field("post_money", "Post-money", "usd0", "pre_money + proceeds", "[$XX,XXX,XXX]"),
            Field("pre_money", "Pre-money", "usd0", "Deck (single consistent figure), --pre-money, or price x "
                  "pre-round outstanding shares", "[$X,XXX,XXX]"),
            Field("pre_money_source", "Pre-money source", "text", "Exact location(s) of the pre-money figure",
                  "[Slide N \"quoted label\"]"),
            Field("proceeds", "Proceeds", "usd0", "Sum of the components below", "[$X,XXX,XXX]"),
            Field("proceeds_breakdown", "Proceeds components", "list",
                  "Issued round cash + commitment rows in Before [+ commitments not in cap table] [+ kept plug "
                  "row] + this check; zero-value optional components omitted",
                  "[issued cash $X; commitment rows $X; this check $X]"),
            Field("implied_pre_basic", "Implied pre-money (outstanding)", "usd0",
                  "price x (Before outstanding - all round shares)", "[$X,XXX,XXX]"),
            Field("implied_pre_fd", "Implied pre-money (fully diluted)", "usd0",
                  "price x (Before fully diluted - all round shares)", "[$X,XXX,XXX]"),
            Field("implied_post_basic", "Implied post-money (outstanding)", "usd0", "price x After outstanding",
                  "[$X,XXX,XXX]"),
            Field("implied_post_fd", "Implied post-money (fully diluted)", "usd0", "price x After fully diluted",
                  "[$X,XXX,XXX]"),
            Field("post_gap", "Gap", "usd0", "implied post (outstanding) - post-money", "[$X,XXX]"),
            Field("bridge_items", "Bridge", "list", "calc.Result.post_bridge items with |value| >= $0.50",
                  "[component $X; component $X]", empty="no difference"),
        ),
        pattern=("{post_money} = pre-money {pre_money} ({pre_money_source}) + proceeds {proceeds} "
                 "({proceeds_breakdown}). Implied priced valuations at {share_price}/share: pre-money "
                 "{implied_pre_basic} on outstanding shares ({implied_pre_fd} fully diluted); post-money "
                 "{implied_post_basic} on outstanding shares ({implied_post_fd} fully diluted). The {post_gap} gap "
                 "to the stated-basis post-money comes from {bridge_items}."),
        rules=("Never label price x outstanding shares as a fully diluted valuation.",),
        style="small",
    ),
    Section(
        "class_table", "Ownership by class: Before (source pro forma) -> After",
        "Every security class in the source, Before and After, with the investor's line kept distinct.",
        columns=("Class", "Before sh.", "Before basic", "Before FD", "After sh.", "After basic", "After FD", "Chg FD"),
        fields=(
            Field("class_rows", "Class rows", "table", "calc.Result.classes in source order: common, preferred "
                  "series, warrants, options/RSUs, unissued pool",
                  "[Class name] | [N,NNN,NNN] | [NN.NN%] | [NN.NN%] | [N,NNN,NNN] | [NN.NN%] | [NN.NN%] | [+N.NNN pp]"),
            Field("total_row", "Total row", "table", "Column totals (fully diluted share counts)",
                  "Total | [NN,NNN,NNN] | 100.00% | 100.00% | [NN,NNN,NNN] | 100.00% | 100.00% |"),
            Field("investor_row", "Investor row", "table", "New-investor row (highlighted)",
                  "of which [Investor name] ([Round label]) | - | - | - | [N,NNN,NNN] | [NN.NN%] | [NN.NN%] | [+N.NNN pp]"),
        ),
        rows="One row per class, then Total (bold), then the investor row (cream, bold).",
        rules=("Basic % columns print 'excl.' for warrants, options/RSUs and the unissued pool.",
               "Share counts: whole numbers without decimals. Change column: percentage points, 3 dp, "
               "'0.000 pp' when the rounded change is zero.",
               "Preferred classes are counted 1:1 as converted."),
        style="table",
    ),
    Section(
        "reconciliation", "", "Tie-out status and how the round adjustments were applied.",
        fields=(
            Field("tie_out_statuses", "Tie-outs", "list", "First three calc checks: outstanding, fully diluted, "
                  "class totals (OK / FAIL)", "[check]: [OK|FAIL]; [check]: [OK|FAIL]; [check]: [OK|FAIL]"),
            Field("plug_clause", "Plug-row clause", "text", "Present only when an unsold plug row is released",
                  " and removes the unsold plug row '[row label]' ([N,NNN,NNN.NN] sh) through a separate adjustment",
                  required=False),
            Field("commitments_clause", "Commitments clause", "text", "Depends on --commitments-in-before",
                  "[Commitments already in the pro forma are not added again. | Commitments not in the cap table "
                  "are added as one aggregate row.]"),
        ),
        pattern=("Before ties to the source: {tie_out_statuses}. {round_label} After includes the new investor"
                 "{plug_clause}. {commitments_clause}"),
        style="small",
    ),
    TOP_ISSUES,
    Section(
        "sources_assumptions", "Sources and assumptions",
        "Every resolved input with its exact source, then the fixed treatment statement.",
        fields=INPUT_FIELDS,
        pattern="{name}: {value} - {source}",
        fixed_text=("Treatment: preferred at 1:1; options/RSUs and pool excluded from basic, included in fully "
                    "diluted; no pool top-up modelled unless sourced; convertibles listed without share counts not "
                    "added."),
        rules=("Items joined inline with bullet separators.",),
        style="notes",
    ),
    DISCLAIMER,
)

# --- blocked variant ---------------------------------------------------------------------------
BLOCKED: tuple[Section, ...] = (
    Section(
        "header", "", "Identifies company, investor and dates (no round terms, no figures).",
        fields=(F_COMPANY, F_ROUND, F_INVESTOR, F_ASOF, F_PREPARED),
        pattern=("{company} - {round_label} investor ownership\n"
                 "Investor: {investor} | Cap table as of {cap_table_as_of} | Prepared {prepared_date}"),
        style="title",
    ),
    Section(
        "status_banner", "", "States plainly that no ownership figure is shown.",
        fixed_text=("Unable to calculate\n"
                    "The sources do not establish every input needed for a reliable ownership figure, so no ownership "
                    "percentage, share count or valuation for this investor is shown. Supply the inputs below and "
                    "rerun."),
        style="banner",
    ),
    Section(
        "required_inputs", "Required inputs", "Each missing or conflicting input, with both conflicting values, "
        "their exact locations, and the CLI flag that resolves it.",
        fields=(Field("missing", "Missing input", "list", "resolve.Inputs.missing",
                      "[Input]: [why it is missing or conflicting, with values and locations]. Supply [--flag]."),),
        pattern="{n}. {missing}",
        rules=("Numbered, one item per missing input, never empty in this variant.",),
    ),
    Section(
        "resolved_inputs", "Inputs that could be resolved", "Inputs the sources did establish.",
        columns=("Input", "Value", "Source"),
        fields=INPUT_FIELDS,
        rows="One row per resolved input.",
        style="table",
    ),
    TOP_ISSUES,
    Section(
        "source_facts", "Source facts (for reference only, not an ownership calculation)",
        "Source totals and tie-out, so the reader knows the cap table itself is readable.",
        fields=(
            Field("source_outstanding", "Source outstanding", "shares", "Cap table total shares outstanding",
                  "[NN,NNN,NNN.NN]"),
            Field("source_outstanding_ref", "Location", "text", "Sheet!Cell", "[Sheet!Cell]"),
            Field("source_fd", "Source fully diluted", "shares", "Cap table fully diluted total", "[NN,NNN,NNN.NN]"),
            Field("source_fd_ref", "Location", "text", "Sheet!Cell", "[Sheet!Cell]"),
            Field("tie_statement", "Tie-out", "text", "Result of independent re-summing",
                  "[both tie to independent sums | differences noted in the workbook]"),
        ),
        pattern=("Source pro forma: {source_outstanding} shares outstanding ({source_outstanding_ref}) and "
                 "{source_fd} fully diluted ({source_fd_ref}); {tie_statement}. Full findings and the live-formula "
                 "model are in the accompanying workbook."),
        style="small",
    ),
    DISCLAIMER,
)

SECTIONS = {"calculated": CALCULATED, "blocked": BLOCKED}

LAYOUT_DIAGRAM = {
    "calculated": """\
+------------------------------------------------------------------------------+
| [Company name] - [Round label] investor ownership                            |
| Investor: [Investor] | Round: [Round share class] | Cap table as of | Prepared |
+---------------+---------------+---------------+---------------+--------------+
| Check size    | New shares    | BASIC OWN.    | Fully diluted | Post-money   |
| [$X,XXX,XXX]  | [N,NNN,NNN.NN]| [NN.NNN%]*    | [NN.NNN%]     | [$XX,XXX,XXX]|
+---------------+---------------+---------------+---------------+--------------+
| Share math sentence                                                          |
| POST-MONEY VALUATION AND BASIS  [pre + proceeds; implied; bridge]            |
| OWNERSHIP BY CLASS: BEFORE -> AFTER                                          |
|  Class | Before sh. | basic | FD | After sh. | basic | FD | Chg FD           |
|  ... one row per class ... | Total | of which [Investor] (highlighted)       |
| Reconciliation sentence                                                      |
| TOP 3 DATA ISSUES  1. 2. 3.                                                  |
| SOURCES AND ASSUMPTIONS  [inputs + sources, treatment]                       |
| Disclaimer                                                                   |
|   [Title]   [Page #]   Compiled on [date] by TEN Capital Network   [logo]    |
+------------------------------------------------------------------------------+
* coral hero value""",
    "blocked": """\
+------------------------------------------------------------------------------+
| [Company name] - [Round label] investor ownership                            |
| Investor: [Investor] | Cap table as of [date] | Prepared [date]              |
| UNABLE TO CALCULATE (coral)                                                  |
| Explanation: no ownership %, share count or valuation is shown               |
| REQUIRED INPUTS          1. [...]  2. [...]                                  |
| INPUTS THAT COULD BE RESOLVED   Input | Value | Source                       |
| TOP 3 DATA ISSUES        1. 2. 3.                                            |
| SOURCE FACTS             [totals, locations, tie-out]                        |
| Disclaimer                                                                   |
|   [Title]   [Page #]   Compiled on [date] by TEN Capital Network   [logo]    |
+------------------------------------------------------------------------------+""",
}

# ---------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------


def section(variant: str, sid: str) -> Section:
    return next(s for s in SECTIONS[variant] if s.id == sid)


def pattern_keys(pattern: str) -> set[str]:
    return set(re.findall(r"{(\w+)}", pattern))


def fill(pattern: str, values: dict) -> str:
    """Pour values into a pattern; a missing required key is an error, never a silent blank."""
    missing = pattern_keys(pattern) - set(values)
    if missing:
        raise KeyError(f"Template pattern needs values for: {', '.join(sorted(missing))}")
    return pattern.format(**values)


def placeholders(variant: str) -> dict[str, str]:
    """Blank-specimen values: every field key mapped to its placeholder text."""
    out: dict[str, str] = {}
    for s in SECTIONS[variant]:
        for f in s.fields:
            out.setdefault(f.key, f.placeholder)
    return out


def to_dict() -> dict:
    return {
        "template": DOCUMENT_TITLE,
        "version": TEMPLATE_VERSION,
        "page": PAGE,
        "fit_scales": list(FIT_SCALES),
        "typography": TYPOGRAPHY,
        "color_roles": COLOR_ROLES,
        "footer": FOOTER,
        "variants": {v: {"when": VARIANTS[v], "layout": LAYOUT_DIAGRAM[v],
                         "sections": [asdict(s) for s in SECTIONS[v]]} for v in SECTIONS},
    }


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " / ")


def to_markdown() -> str:
    lines = [
        f"# {DOCUMENT_TITLE} - Document Structure Template",
        "",
        f"Template version {TEMPLATE_VERSION}. Generated from `templates/document_structure.py` by "
        "`python -m templates.generate_template`; edit the Python module, not this file.",
        "",
        "This template defines the structure, fields, formats, sources and rules of every one-page investor "
        "ownership summary the app generates. It contains no company data: values in square brackets are "
        "placeholders.",
        "",
        "## Page specification",
        "",
        "| Property | Value |",
        "| --- | --- |",
    ]
    for k, v in PAGE.items():
        lines.append(f"| {k} | {_md_escape(str(v))} |")
    lines += ["", f"Fit scales, tried in order: {', '.join(str(x) for x in FIT_SCALES)}.", "",
              "## Typography", "", "| Element | Value |", "| --- | --- |"]
    lines += [f"| {k} | {_md_escape(str(v))} |" for k, v in TYPOGRAPHY.items()]
    lines += ["", "## Colour roles", "", "| Token | Hex | Role |", "| --- | --- | --- |"]
    lines += [f"| {k} | `{v['hex']}` | {v['role']} |" for k, v in COLOR_ROLES.items()]
    lines += ["", "## Footer", "", "| Property | Value |", "| --- | --- |"]
    lines += [f"| {k} | {_md_escape(v)} |" for k, v in FOOTER.items()]
    for variant, secs in SECTIONS.items():
        lines += ["", f"## Variant: {variant}", "", VARIANTS[variant], "", "```", LAYOUT_DIAGRAM[variant], "```", ""]
        for i, s in enumerate(secs, 1):
            lines += [f"### {i}. {s.heading or s.id.replace('_', ' ').title()}  (`{s.id}`)", "", s.purpose, ""]
            if s.pattern:
                lines += ["Pattern:", "", "```", s.pattern, "```", ""]
            if s.columns:
                lines += ["Columns: " + " | ".join(s.columns), ""]
            if s.rows:
                lines += [f"Rows: {s.rows}", ""]
            if s.fields:
                lines += ["| Field | Label | Format | Source | Placeholder | Required | Empty state |",
                          "| --- | --- | --- | --- | --- | --- | --- |"]
                for f in s.fields:
                    lines.append(f"| `{f.key}` | {_md_escape(f.label)} | {f.fmt} | {_md_escape(f.source)} | "
                                 f"{_md_escape(f.placeholder)} | {'yes' if f.required else 'no'} | "
                                 f"{_md_escape(f.empty) or '-'} |")
                lines.append("")
            if s.fixed_text:
                lines += ["Fixed text:", "", "> " + s.fixed_text.replace("\n", "\n> "), ""]
            for r in s.rules:
                lines.append(f"- {r}")
            if s.rules:
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"
