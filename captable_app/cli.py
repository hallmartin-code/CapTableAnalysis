"""Command-line entry point: python -m captable_app --cap-table X.xlsx --deck Y.pptx ..."""
from __future__ import annotations

import argparse
import os
import re
import sys

from .fmt import pct, pp, sh, usd
from .pipeline import analyze


def _money(s: str) -> float:
    v = float(re.sub(r"[,$\s]", "", s))
    if v < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return v


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="captable_app",
                                description="New-investor ownership in a priced preferred round from a pro forma cap "
                                            "table (.xlsx) and a pitch deck (.pdf/.pptx).")
    p.add_argument("--cap-table", required=True, help="Source pro forma cap table (.xlsx)")
    p.add_argument("--deck", required=True, help="Source pitch deck (.pdf or .pptx)")
    p.add_argument("--investor", default=None, help="Investor name (default 'New investor')")
    p.add_argument("--check-size", type=_money, default=None,
                   help="USD. If omitted, the full open allocation is used only when the sources state it unambiguously")
    p.add_argument("--share-price", type=_money, default=None,
                   help="USD per share. If omitted, the cap table's round issue price is used")
    p.add_argument("--commitments-in-before", choices=["yes", "no"], default=None,
                   help="Are all existing round commitments already in the pro forma? Required when the sources "
                        "do not establish it")
    p.add_argument("--uncounted-commitments", type=_money, default=None,
                   help="USD of round commitments NOT in the cap table (required with --commitments-in-before no)")
    p.add_argument("--open-allocation-placeholder", choices=["release", "keep"], default="release",
                   help="Treatment of an unsold 'remaining round' plug row in the source: release it in After "
                        "(default) or keep it (investor shares then stack on top of it)")
    p.add_argument("--pre-money", type=_money, default=None, help="Override the priced pre-money valuation (USD)")
    p.add_argument("--output-dir", required=True, help="Destination folder for the workbook and PDF")
    p.add_argument("--ai-review", action="store_true",
                   help="Send the extracted sources and image-only slides to the Claude API for an additional "
                        "evidence-checked review (needs ANTHROPIC_API_KEY). Numbers are never taken from the AI.")
    p.add_argument("--email", action="store_true",
                   help="Email the results (PDF + workbook attached) via Resend to RESEND_TO "
                        "(default Info@tencapital.group); needs RESEND_API_KEY")
    p.add_argument("--verify", action="store_true",
                   help="After writing, verify the outputs (formula references, independent recalculation if the "
                        "'formulas' package is installed, one-page PDF)")
    return p


def run(argv=None) -> int:
    a = build_parser().parse_args(argv)
    for path, exts in ((a.cap_table, (".xlsx",)), (a.deck, (".pdf", ".pptx"))):
        if not os.path.isfile(path):
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
        if os.path.splitext(path)[1].lower() not in exts:
            print(f"ERROR: {path} must be one of {exts}", file=sys.stderr)
            return 1

    r = analyze(a.cap_table, a.deck, a.output_dir, investor=a.investor, check_size=a.check_size,
                share_price=a.share_price, commitments_in_before=a.commitments_in_before,
                uncounted_commitments=a.uncounted_commitments, placeholder_mode=a.open_allocation_placeholder,
                pre_money=a.pre_money, ai_review=a.ai_review, verify=a.verify,
                progress=lambda s: print(f"... {s}", file=sys.stderr))

    print(f"\n{r.company} - {r.round_label} ownership\n" + "=" * 60)
    print("Resolved inputs:")
    for x in r.inputs.resolved:
        val = f"{x.value:,.6g}" if isinstance(x.value, float) and x.value < 10 else (
            f"{x.value:,.2f}" if isinstance(x.value, float) else x.value)
        print(f"  - {x.name}: {val}\n      source: {x.source}")
    print("\nTop data issues:")
    for n, i in enumerate(r.top_issues, 1):
        print(f"  {n}. [{i.severity}] {i.title}\n     {'; '.join(i.refs[:4])}")
    if r.ai is not None and not r.ai_error:
        print(f"\nClaude review: {len(r.ai.findings)} verified finding(s), {len(r.ai.discarded)} discarded, "
              f"{len(r.ai.image_figures)} image figure(s). {r.ai.summary}")
    elif r.ai_error:
        print(f"\nClaude review: {r.ai_error}")

    if r.status == "blocked":
        print("\nUNABLE TO CALCULATE - required inputs:")
        for m in r.missing:
            print(f"  - {m}")
    else:
        res, iv = r.result, r.result.investor_row
        print(f"\nNew {r.round_label} shares: {sh(res.new_shares, 6)} (unrounded)")
        print(f"Ownership: basic {pct(iv.pct_after_basic, 3)}, fully diluted {pct(iv.pct_after_fd, 3)}")
        print(f"Post-money (pre + proceeds): {usd(res.valuation['post_money'])}")
        print("\nBy class (After FD % | change pp):")
        for c in res.classes:
            print(f"  {c.name:<50} {sh(c.before):>16} -> {sh(c.after):>16}  {pct(c.pct_after_fd)} "
                  f"({pp(c.pct_after_fd - c.pct_before_fd, 3)})")
        for name, ok, detail in res.checks:
            print(f"  [{'OK' if ok else 'FLAG'}] {name}: {detail}")
        for w in res.warnings:
            print(f"  WARNING: {w}")
    if r.verification:
        print("\nVerification:")
        for name, ok, detail in r.verification:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name} - {detail}")
    if a.email:
        from .notify import send_results
        print("\n" + send_results(r).note)
    print(f"\nWorkbook: {os.path.abspath(r.xlsx)}\nPDF: {os.path.abspath(r.pdf)}")
    return 2 if r.status == "blocked" else 0


def main():
    try:
        from dotenv import load_dotenv   # local development only; production uses real env vars
        load_dotenv()
    except ImportError:
        pass
    sys.exit(run())
