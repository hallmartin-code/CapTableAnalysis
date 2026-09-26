"""The document structure template: company-free, internally consistent, and actually used by the app."""
import json
import re
from pathlib import Path

import pymupdf
import pytest

from captable_app.pdf_report import render
from templates import document_structure as T
from templates.generate_template import generate, specimen_content

from conftest import CAP_XLSX, DECK_PPTX, real_sources

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    out = tmp_path_factory.mktemp("tpl")
    generate(out)
    return out


def _artifact_text(out: Path) -> str:
    parts = [(ROOT / "templates" / "document_structure.py").read_text(encoding="utf-8")]
    for p in out.iterdir():
        if p.suffix == ".pdf":
            parts += [pg.get_text() for pg in pymupdf.open(str(p))]
        elif p.suffix in (".md", ".json"):
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_pattern_key_is_a_declared_field():
    for variant, sections in T.SECTIONS.items():
        values = specimen_content(variant)
        for s in sections:
            if s.pattern and s.id not in ("top_issues", "sources_assumptions", "required_inputs"):
                assert T.pattern_keys(s.pattern) <= set(values), (variant, s.id)


def test_specimens_are_one_page_and_placeholder_only(artifacts):
    for name in ("INVESTOR_OWNERSHIP_SUMMARY_TEMPLATE.pdf", "INVESTOR_OWNERSHIP_SUMMARY_BLOCKED_TEMPLATE.pdf"):
        with pymupdf.open(str(artifacts / name)) as d:
            assert d.page_count == 1
            text = d[0].get_text()
            assert "[Company name]" in text and "[Investor name]" in text
            assert not re.search(r"\$\d", text), "specimen contains a real dollar figure"
    spec = json.loads((artifacts / "investor_ownership_summary.template.json").read_text(encoding="utf-8"))
    assert set(spec["variants"]) == {"calculated", "blocked"}


def test_template_contains_no_generic_company_figures(artifacts):
    text = _artifact_text(artifacts)
    for token in ("Seed-3", "0.8293", "0.8923", "Intermediate!", "Summary!F13", "Slide 19"):
        assert token not in text, token


@real_sources
def test_template_contains_nothing_from_the_supplied_sources(artifacts):
    from captable_app.extract_deck import extract_deck
    from captable_app.extract_xlsx import extract_workbook
    from captable_app.normalize import parse_cap_table, parse_deck_terms
    cap = parse_cap_table(extract_workbook(CAP_XLSX))
    deck = parse_deck_terms(extract_deck(DECK_PPTX))
    text = _artifact_text(artifacts).lower()
    tokens = {cap.company, cap.company.split()[0]} | {r.name for r in cap.rows if r.row_type == "holder"}
    tokens |= {lead for lead, _ in deck.lead_investor}
    for t in tokens:
        assert t.lower() not in text, t


def test_render_refuses_missing_required_fields(tmp_path):
    c = specimen_content("calculated")
    del c["post_money"]
    with pytest.raises(KeyError, match="post_money"):
        render(str(tmp_path / "x.pdf"), "calculated", c)
    b = specimen_content("blocked")
    b["missing"] = []
    with pytest.raises(KeyError, match="missing"):
        render(str(tmp_path / "y.pdf"), "blocked", b)


@real_sources
def test_generated_reports_follow_template_section_order(tmp_path):
    from captable_app.cli import run
    for args, variant in (([], "blocked"), (["--check-size", "900000", "--commitments-in-before", "yes"], "calculated")):
        out = tmp_path / variant
        run(["--cap-table", CAP_XLSX, "--deck", DECK_PPTX, "--output-dir", str(out)] + args)
        pdf = next(out.glob("*.pdf"))
        text = pymupdf.open(str(pdf))[0].get_text()
        positions = [text.find(s.heading) for s in T.SECTIONS[variant] if s.heading]
        assert all(p >= 0 for p in positions), positions
        assert positions == sorted(positions)
