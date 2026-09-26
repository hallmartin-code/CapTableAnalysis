# Seed-3 new-investor ownership calculator

Computes the ownership a new investor receives in a Series Seed-3 round from a pro forma
cap table (`.xlsx`) and a pitch deck (`.pptx` or `.pdf`). Produces a live-formula Excel
workbook and a one-page PDF summary. Everything runs locally; no file is sent anywhere.

```
python -m captable_app --cap-table inputs/<cap table>.xlsx --deck inputs/<deck>.pptx \
    --output-dir output [--investor NAME] [--check-size USD] [--share-price USD] \
    [--commitments-in-before yes|no] [--uncounted-commitments USD] \
    [--open-allocation-placeholder release|keep] [--pre-money USD] [--verify]
```

Exit code 0 = calculated, 2 = blocked (the PDF becomes an "Unable to calculate" report and
the workbook shows BLOCKED until the missing inputs are entered).

| Module | Role |
|---|---|
| `extract_xlsx.py` | every cell's formula and cached value, sheet states, hidden rows/cols, named ranges |
| `extract_deck.py` | slide/page text, tables, charts, speaker notes, picture coverage |
| `normalize.py` | Carta-style Summary/Intermediate layout -> classes, holder rows, round cash; deck round terms |
| `validate.py` | formula errors, circular refs, broken names, tie-outs, deck-vs-cap-table mismatches |
| `resolve.py` | each input's value and exact source, or why it is missing |
| `calc.py` | Before/After, basic and fully diluted ownership, valuation and bridge (pure functions) |
| `workbook.py` / `pdf_report.py` | deliverables |
| `verify.py` | formula-reference checks, independent recalculation (`formulas`), one-page PDF check |

Tests: `pip install -r requirements-dev.txt; python -m pytest -q` (integration tests run only when the source
files are in `inputs/`; no test calls the Claude API).

## Claude AI review (`--ai-review`, on by default in the web app)

`captable_app/ai_review.py` sends the extracted cell listing, slide text and the image-only slides to the Claude
API (`claude-opus-5`, adaptive thinking, structured JSON output, server-side refusal fallback). Claude reports
figures it can read only in images and extra source problems, each with a verbatim quote. The app keeps a
finding only if the quote is found in the extracted source (image evidence is kept but capped at MEDIUM and
labelled for manual check). Image figures can raise conflicts but never resolve an input. Claude never
produces a calculated number. Every AI run writes `<report>_ai_review.json` with the raw output and the
verification result of each quote. Key: `ANTHROPIC_API_KEY` in `.env` (local) or a Railway variable.

## Email results (Resend)

`captable_app/notify.py` emails every finished web analysis (calculated or blocked, plus a short notice if a run
crashes) to `RESEND_TO` (default Info@tencapital.group) from `RESEND_FROM`
(default `ownership@tencapital.group`; the domain is verified in Resend). The email has the headline figures,
by-class table or missing inputs, top 3 data issues, the Claude summary, inputs with sources, and a link to the
results page. Attached: PDF, workbook and the AI review JSON when Claude ran. The uploaded cap table and deck are
never attached. Email failures are logged and shown on the results page but never fail the analysis.
CLI: add `--email`. Tests never send email (the Resend key is removed from the environment during tests).

## Web app and Railway

Local: `uvicorn captable_app.web:app --port 8000` (reads `.env`).
Production: Railway project `investor-ownership-calculator`, service `ownership-web`,
https://ownership-web-production.up.railway.app (open access, no login).
Redeploy from this folder with:

```
railway up . --path-as-root --service ownership-web --ci
```

`--path-as-root` matters: this folder sits inside a larger git repository, and it keeps the upload to this
folder only. `.railwayignore` excludes `.env`, `inputs/`, `output/` and tests. Variables: `ANTHROPIC_API_KEY`,
`RESEND_API_KEY`, `RESEND_TO`, `RESEND_FROM`, `CLAUDE_MODEL`, `CLAUDE_EFFORT`, `MAX_UPLOAD_MB` (200), `JOB_TTL_MINUTES` (60), `AI_REVIEW_DEFAULT`.

## Document structure template

`templates/document_structure.py` is the single source of truth for the one-page PDF: the two
variants (calculated / blocked), section order, headings, fields (format, source, required,
empty state, placeholder), sentence patterns, table columns, fixed text, page and fit rules.
`captable_app/pdf_report.py` renders every report from it and refuses content missing a
required field. Regenerate the blank artifacts after changing it:

```
python -m templates.generate_template
```

Writes `INVESTOR_OWNERSHIP_SUMMARY_TEMPLATE.{pdf,png,md}`, the blocked-variant specimen and
`investor_ownership_summary.template.json` into `templates/`. They contain placeholders only.
