"""End-to-end run shared by the CLI and the web app.

extract -> normalize -> rule-based review -> (optional) Claude review -> re-review with image figures
-> resolve inputs -> calculate (or block) -> workbook + one-page PDF -> (optional) verification.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .calc import CalculationBlocked, Result, calculate
from .extract_deck import extract_deck
from .extract_xlsx import extract_workbook
from .models import Inputs, Issue, ResolvedInput
from .normalize import parse_cap_table, parse_deck_terms
from .pdf_report import default_logo, round_labels, write_blocked_pdf, write_pdf
from .resolve import resolve_inputs
from .validate import review_sources
from .workbook import write_workbook

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    status: str                      # "calculated" or "blocked"
    company: str
    round_label: str
    xlsx: str
    pdf: str
    inputs: Inputs
    top_issues: list[Issue]
    result: Optional[Result] = None
    ai: object = None                # AIReviewResult when the Claude review ran
    ai_error: Optional[str] = None
    verification: list = field(default_factory=list)

    @property
    def missing(self) -> list[str]:
        return self.inputs.missing


def analyze(cap_path: str, deck_path: str, out_dir: str, *, investor: Optional[str] = None,
            check_size: Optional[float] = None, share_price: Optional[float] = None,
            commitments_in_before: Optional[str] = None, uncounted_commitments: Optional[float] = None,
            placeholder_mode: str = "release", pre_money: Optional[float] = None,
            ai_review: bool = False, verify: bool = False,
            progress: Callable[[str], None] = lambda s: None) -> RunResult:
    os.makedirs(out_dir, exist_ok=True)
    progress("Reading cap table and deck")
    wb = extract_workbook(cap_path)
    cap = parse_cap_table(wb)
    deck_dump = extract_deck(deck_path)
    deck = parse_deck_terms(deck_dump)
    progress("Running source checks")
    review = review_sources(wb, cap, deck)

    ai, ai_error = None, None
    if ai_review:
        progress("Claude is reviewing the sources (this can take a few minutes)")
        try:
            from .ai_review import AIReviewUnavailable, apply_image_figures, run_ai_review
            ai = run_ai_review(wb, deck_dump, deck, review)
            ai_error = ai.error
            if ai.image_figures:
                apply_image_figures(deck, ai.image_figures)
                review = review_sources(wb, cap, deck)      # re-run so image figures raise conflicts
            review.issues.extend(ai.findings)
        except AIReviewUnavailable as e:
            ai_error = f"not run: {e}"
        except Exception as e:  # network/API failure must not block the deterministic analysis
            log.exception("Claude review failed")
            ai_error = f"not run: {type(e).__name__}: {str(e)[:200]}"

    progress("Resolving inputs and calculating")
    inp = resolve_inputs(investor=investor, check_size=check_size, share_price=share_price,
                         commitments_in_before=commitments_in_before, uncounted_commitments=uncounted_commitments,
                         placeholder_mode=placeholder_mode, pre_money=pre_money, cap=cap, deck=deck, review=review)
    if ai_review:
        if ai is not None and not ai.error:
            inp.resolved.append(ResolvedInput(
                "AI review", f"{len(ai.findings)} verified finding(s), {len(ai.image_figures)} image figure(s)",
                f"Claude API ({ai.served_by or ai.model}); {len(ai.discarded)} finding(s) discarded because their "
                f"quoted evidence was not found in the sources; AI does not change any calculated figure"))
        else:
            inp.resolved.append(ResolvedInput("AI review", "not included", f"Claude API: {ai_error}"))

    short, _ = round_labels(cap)
    base = re.sub(r"[^A-Za-z0-9]+", "_", f"{cap.company} {short} Ownership").strip("_")
    xlsx, pdf = os.path.join(out_dir, base + ".xlsx"), os.path.join(out_dir, base + ".pdf")
    top = review.top(3)

    progress("Writing workbook and PDF")
    try:
        res = calculate(cap, inp, review.derived)
    except CalculationBlocked:
        res = None
    layout = write_workbook(xlsx, cap, deck, inp, review, ai=ai, ai_error=ai_error)
    if res is None:
        write_blocked_pdf(pdf, cap, deck, inp, top, review.derived, default_logo())
    else:
        write_pdf(pdf, cap, deck, inp, res, top, default_logo())

    if ai is not None and ai.raw:
        import json
        with open(os.path.join(out_dir, base + "_ai_review.json"), "w", encoding="utf-8") as fh:
            json.dump({"model": ai.model, "served_by": ai.served_by, "usage": ai.usage, "images_sent": ai.images_sent,
                       **ai.raw}, fh, indent=2, ensure_ascii=False)
    run = RunResult("blocked" if res is None else "calculated", cap.company, short, xlsx, pdf, inp, top, res,
                    ai, ai_error)
    if verify:
        progress("Verifying outputs")
        from .verify import verify_outputs
        run.verification = verify_outputs(xlsx, pdf, cap, inp, res, layout)
    progress("Done")
    return run
