"""Generate the blank Investor Ownership Summary template artifacts.

    python -m templates.generate_template            # writes into templates/
    python -m templates.generate_template --out DIR

Outputs (no company data - placeholders only):
  * INVESTOR_OWNERSHIP_SUMMARY_TEMPLATE.pdf           blank calculated-variant specimen (real renderer)
  * INVESTOR_OWNERSHIP_SUMMARY_BLOCKED_TEMPLATE.pdf   blank 'Unable to calculate' specimen (real renderer)
  * *.png                                             previews of both specimens
  * INVESTOR_OWNERSHIP_SUMMARY_TEMPLATE.md            human-readable structure specification
  * investor_ownership_summary.template.json          machine-readable structure specification
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python templates/generate_template.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captable_app.pdf_report import default_logo, render  # noqa: E402
from templates import document_structure as T  # noqa: E402

BASENAME = "INVESTOR_OWNERSHIP_SUMMARY"


def _split(placeholder: str) -> list[str]:
    return [c.strip() for c in placeholder.split("|")]


def specimen_content(variant: str) -> dict:
    """Placeholder values for every field in the variant, including list and table fields."""
    c = T.placeholders(variant)
    issue = {f.key: f.placeholder for f in T.TOP_ISSUES.fields}
    c["top_issues"] = [dict(issue) for _ in range(3)]
    inp = {f.key: f.placeholder for f in T.INPUT_FIELDS}
    c["resolved_inputs"] = [dict(inp) for _ in range(3)]
    if variant == "calculated":
        tbl = {f.key: f.placeholder for f in T.section("calculated", "class_table").fields}
        kinds = ["[Common class]", "[Preferred series 1]", "[Preferred series n]", "[Round class]",
                 "[Warrants]", "[Options & RSUs outstanding]", "[Unissued option pool]"]
        row = _split(tbl["class_rows"])
        c["class_rows"] = [[k] + [("excl." if i in (1, 4) and k in kinds[4:] else x)
                                  for i, x in enumerate(row[1:])] for k in kinds]
        c["total_row"] = _split(tbl["total_row"])
        c["investor_row"] = _split(tbl["investor_row"])
    else:
        c["missing"] = [T.section("blocked", "required_inputs").fields[0].placeholder] * 2
    return c


def generate(out_dir: Path) -> list[Path]:
    import pymupdf
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for variant, name in (("calculated", f"{BASENAME}_TEMPLATE"), ("blocked", f"{BASENAME}_BLOCKED_TEMPLATE")):
        pdf = out_dir / f"{name}.pdf"
        render(str(pdf), variant, specimen_content(variant), default_logo(), compiled="[Month DD, YYYY]")
        png = out_dir / f"{name}.png"
        with pymupdf.open(str(pdf)) as d:
            d[0].get_pixmap(dpi=110).save(str(png))
        written += [pdf, png]
    md = out_dir / f"{BASENAME}_TEMPLATE.md"
    md.write_text(T.to_markdown(), encoding="utf-8")
    js = out_dir / "investor_ownership_summary.template.json"
    js.write_text(json.dumps(T.to_dict(), indent=2), encoding="utf-8")
    return written + [md, js]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    for p in generate(Path(ap.parse_args(argv).out)):
        print(p)


if __name__ == "__main__":
    main()
