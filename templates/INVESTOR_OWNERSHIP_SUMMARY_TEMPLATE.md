# Investor Ownership Summary - Document Structure Template

Template version 1.0. Generated from `templates/document_structure.py` by `python -m templates.generate_template`; edit the Python module, not this file.

This template defines the structure, fields, formats, sources and rules of every one-page investor ownership summary the app generates. It contains no company data: values in square brackets are placeholders.

## Page specification

| Property | Value |
| --- | --- |
| size | US Letter |
| orientation | portrait |
| width_pt | 612 |
| height_pt | 792 |
| margins_in | {'left': 0.6, 'right': 0.6, 'top': 0.5, 'bottom': 0.85} |
| pages | 1 |
| overflow_rule | Render, count pages, and step down through FIT_SCALES until the report is exactly one page. If the smallest scale still overflows, fail instead of saving. |

Fit scales, tried in order: 1.1, 1.05, 1.0, 0.96, 0.92, 0.88, 0.84, 0.8, 0.76.

## Typography

| Element | Value |
| --- | --- |
| family | Helvetica / Helvetica-Bold (Inter or Open Sans when embedded) |
| title_pt | 17 |
| subtitle_pt | 9 |
| section_heading_pt | 10.5 |
| body_pt | 8.3 |
| small_pt | 7.4 |
| notes_pt | 6.2 |
| table_pt | 7.3 |
| metric_label_pt | 7.4 |
| metric_value_pt | 15 |
| hero_value_pt | 17 |
| blocked_banner_pt | 22 |
| footer_pt | 7 |
| scaling | All sizes except the footer are multiplied by the active fit scale; metric values never scale above 1.0 |
| minimum_readable_pt | 6.5 |

## Colour roles

| Token | Hex | Role |
| --- | --- | --- |
| ink | `#000000` | Title, headings, metric values, bold table rows |
| body | `#4B4F58` | Body copy and table cells |
| muted | `#7A7A7A` | Subtitle, source locations, notes, disclaimer, footer text |
| coral | `#ED5644` | Hero metric (basic ownership) and the 'Unable to calculate' banner only |
| rule | `#CBD6E2` | Table row dividers, metric box border, footer rule |
| gray_bg | `#F7F7F7` | Table header fill |
| cream | `#FFFDF6` | Metric strip background; new-investor table row |

## Footer

| Property | Value |
| --- | --- |
| pattern | [Document title]   [Page #]   Compiled on [Month DD, YYYY] by TEN Capital Network   [TEN Capital logo] |
| document_title | [Company name] [Round label] Investor Ownership Summary |
| document_title_blocked | [Company name] [Round label] Ownership - Unable to Calculate |
| font | 7 pt, centred, muted |
| logo | assets/TEN_Capital_logo_footer.png at 0.67 x 0.25 in |
| rule | 0.5 pt hairline above the footer |

## Variant: calculated

All inputs resolved; ownership calculated.

```
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
* coral hero value
```

### 1. Header  (`header`)

Identifies company, round, investor and dates.

Pattern:

```
{company} - {round_label} investor ownership
Investor: {investor} | Round: {round_class_name} (priced) | Cap table as of {cap_table_as_of} | Prepared {prepared_date}
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `company` | Company | text | Cap table title cell (text before 'Cap Table') | [Company name] | yes | - |
| `round_label` | Round | text | Name of the round share class in the cap table header, without the 'Preferred (code)' suffix | [Round label] | yes | - |
| `investor` | Investor | text | --investor (default 'New investor') | [Investor name] | yes | - |
| `round_class_name` | Round security | text | Full round share-class name from the cap table | [Round share class] | yes | - |
| `cap_table_as_of` | Cap table as of | date | Cap table 'As of' line | [M/D/YYYY] | no | date not stated |
| `prepared_date` | Prepared | date | Run date | [Month DD, YYYY] | yes | - |

### 2. Key Metrics  (`key_metrics`)

Five headline figures in one strip; basic ownership is the single coral hero value.

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `check_size` | Check size | usd0 | --check-size, or the full open allocation when stated unambiguously | [$ amount] | yes | - |
| `new_shares` | New {round_label} shares | shares | check size / share price (unrounded) | [shares] | yes | - |
| `basic_ownership` | Basic ownership | pct3 | Investor After shares / After issued and outstanding shares | [NN.NNN%] | yes | - |
| `fd_ownership` | Fully diluted ownership | pct3 | Investor After shares / After fully diluted shares | [NN.NNN%] | yes | - |
| `post_money` | Post-money valuation | usd0 | Priced pre-money + proceeds in the modelled financing | [$ amount] | yes | - |

- Labels on one line, values on the next, centred, five equal columns.

### 3. Share Math  (`share_math`)

Shows how the new share count was derived and what each ownership basis contains.

Pattern:

```
New shares = {check_size_exact} / {share_price} = {new_shares_exact} (unrounded; {fraction_note}). Basic = issued and outstanding common + preferred ({after_basic_shares} after); fully diluted adds options/RSUs and the unissued pool ({after_fd_shares} after).
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `check_size_exact` | Check size | usd2 | Resolved input | [$X,XXX,XXX.XX] | yes | - |
| `share_price` | Share price | usd4 | Cap-table round issue price, or --share-price | [$N.NNNN] | yes | - |
| `new_shares_exact` | New shares (4 dp) | shares4 | check / price, unrounded | [N,NNN,NNN.NNNN] | yes | - |
| `fraction_note` | Fractional-share note | text | Stated convention, else the confirmation note | [fractional-share convention or confirmation note] | yes | - |
| `after_basic_shares` | After outstanding shares | shares | Sum of After basic column | [NN,NNN,NNN.NN] | yes | - |
| `after_fd_shares` | After fully diluted shares | shares | Sum of After FD column | [NN,NNN,NNN.NN] | yes | - |

### 4. Post-money valuation and basis  (`valuation`)

States the post-money, its components and source, the implied priced valuations on both share bases, and a bridge that explains every dollar of difference.

Pattern:

```
{post_money} = pre-money {pre_money} ({pre_money_source}) + proceeds {proceeds} ({proceeds_breakdown}). Implied priced valuations at {share_price}/share: pre-money {implied_pre_basic} on outstanding shares ({implied_pre_fd} fully diluted); post-money {implied_post_basic} on outstanding shares ({implied_post_fd} fully diluted). The {post_gap} gap to the stated-basis post-money comes from {bridge_items}.
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `post_money` | Post-money | usd0 | pre_money + proceeds | [$XX,XXX,XXX] | yes | - |
| `pre_money` | Pre-money | usd0 | Deck (single consistent figure), --pre-money, or price x pre-round outstanding shares | [$X,XXX,XXX] | yes | - |
| `pre_money_source` | Pre-money source | text | Exact location(s) of the pre-money figure | [Slide N "quoted label"] | yes | - |
| `proceeds` | Proceeds | usd0 | Sum of the components below | [$X,XXX,XXX] | yes | - |
| `proceeds_breakdown` | Proceeds components | list | Issued round cash + commitment rows in Before [+ commitments not in cap table] [+ kept plug row] + this check; zero-value optional components omitted | [issued cash $X; commitment rows $X; this check $X] | yes | - |
| `implied_pre_basic` | Implied pre-money (outstanding) | usd0 | price x (Before outstanding - all round shares) | [$X,XXX,XXX] | yes | - |
| `implied_pre_fd` | Implied pre-money (fully diluted) | usd0 | price x (Before fully diluted - all round shares) | [$X,XXX,XXX] | yes | - |
| `implied_post_basic` | Implied post-money (outstanding) | usd0 | price x After outstanding | [$X,XXX,XXX] | yes | - |
| `implied_post_fd` | Implied post-money (fully diluted) | usd0 | price x After fully diluted | [$X,XXX,XXX] | yes | - |
| `post_gap` | Gap | usd0 | implied post (outstanding) - post-money | [$X,XXX] | yes | - |
| `bridge_items` | Bridge | list | calc.Result.post_bridge items with \|value\| >= $0.50 | [component $X; component $X] | yes | no difference |

- Never label price x outstanding shares as a fully diluted valuation.

### 5. Ownership by class: Before (source pro forma) -> After  (`class_table`)

Every security class in the source, Before and After, with the investor's line kept distinct.

Columns: Class | Before sh. | Before basic | Before FD | After sh. | After basic | After FD | Chg FD

Rows: One row per class, then Total (bold), then the investor row (cream, bold).

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `class_rows` | Class rows | table | calc.Result.classes in source order: common, preferred series, warrants, options/RSUs, unissued pool | [Class name] \| [N,NNN,NNN] \| [NN.NN%] \| [NN.NN%] \| [N,NNN,NNN] \| [NN.NN%] \| [NN.NN%] \| [+N.NNN pp] | yes | - |
| `total_row` | Total row | table | Column totals (fully diluted share counts) | Total \| [NN,NNN,NNN] \| 100.00% \| 100.00% \| [NN,NNN,NNN] \| 100.00% \| 100.00% \| | yes | - |
| `investor_row` | Investor row | table | New-investor row (highlighted) | of which [Investor name] ([Round label]) \| - \| - \| - \| [N,NNN,NNN] \| [NN.NN%] \| [NN.NN%] \| [+N.NNN pp] | yes | - |

- Basic % columns print 'excl.' for warrants, options/RSUs and the unissued pool.
- Share counts: whole numbers without decimals. Change column: percentage points, 3 dp, '0.000 pp' when the rounded change is zero.
- Preferred classes are counted 1:1 as converted.

### 6. Reconciliation  (`reconciliation`)

Tie-out status and how the round adjustments were applied.

Pattern:

```
Before ties to the source: {tie_out_statuses}. {round_label} After includes the new investor{plug_clause}. {commitments_clause}
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `tie_out_statuses` | Tie-outs | list | First three calc checks: outstanding, fully diluted, class totals (OK / FAIL) | [check]: [OK\|FAIL]; [check]: [OK\|FAIL]; [check]: [OK\|FAIL] | yes | - |
| `plug_clause` | Plug-row clause | text | Present only when an unsold plug row is released |  and removes the unsold plug row '[row label]' ([N,NNN,NNN.NN] sh) through a separate adjustment | no | - |
| `commitments_clause` | Commitments clause | text | Depends on --commitments-in-before | [Commitments already in the pro forma are not added again. \| Commitments not in the cap table are added as one aggregate row.] | yes | - |

### 7. Top 3 data issues  (`top_issues`)

The three most material source problems: severity first, then materiality priority. INFO items never appear.

Pattern:

```
{n}. {title} [{severity}] - {evidence} Source: {sources}.
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `title` | Finding | text | validate.Issue.title (generated from the values found) | [Finding title] | yes | - |
| `severity` | Severity | text | HIGH / MEDIUM / LOW | HIGH\|MEDIUM\|LOW | yes | - |
| `evidence` | Evidence | text | Issue arithmetic, else detail | [Both values and the arithmetic] | yes | - |
| `sources` | Source | text | Up to four exact locations (Sheet!Cell, Slide N) | [Sheet!Cell; Slide N] | yes | - |

- Exactly three items when three or more non-INFO issues exist; fewer otherwise.
- Empty state: 'No material data issues found.'

### 8. Sources and assumptions  (`sources_assumptions`)

Every resolved input with its exact source, then the fixed treatment statement.

Pattern:

```
{name}: {value} - {source}
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | Input | text | resolve.ResolvedInput.name | [Input name] | yes | - |
| `value` | Value | text | Resolved value | [Value] | yes | - |
| `source` | Source | text | Workbook, tab and cell, deck slide and quoted label, or CLI flag | [File \| Location "quoted label"] | yes | - |

Fixed text:

> Treatment: preferred at 1:1; options/RSUs and pool excluded from basic, included in fully diluted; no pool top-up modelled unless sourced; convertibles listed without share counts not added.

- Items joined inline with bullet separators.

### 9. Disclaimer  (`disclaimer`)

TEN standard disclaimer, required on investment-related documents.

Fixed text:

> Disclaimer: TEN is a "Funding as a Service" program. It is not a registered broker-dealer and does not offer investment advice or advise on the raising of capital through securities offerings. TEN does not recommend or otherwise suggest that any investor make an investment in a specific company, or that any company offer securities to a particular investor. TEN takes no part in the negotiation or execution of transactions for the purchase or sale of securities, and at no time has possession of funds or securities. No securities transactions are executed or negotiated on or through the TEN program. TEN receives no compensation in connection with the purchase or sale of securities.


## Variant: blocked

A required input is missing or conflicting. No ownership percentage, share count or valuation for the investor may appear anywhere on the page.

```
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
+------------------------------------------------------------------------------+
```

### 1. Header  (`header`)

Identifies company, investor and dates (no round terms, no figures).

Pattern:

```
{company} - {round_label} investor ownership
Investor: {investor} | Cap table as of {cap_table_as_of} | Prepared {prepared_date}
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `company` | Company | text | Cap table title cell (text before 'Cap Table') | [Company name] | yes | - |
| `round_label` | Round | text | Name of the round share class in the cap table header, without the 'Preferred (code)' suffix | [Round label] | yes | - |
| `investor` | Investor | text | --investor (default 'New investor') | [Investor name] | yes | - |
| `cap_table_as_of` | Cap table as of | date | Cap table 'As of' line | [M/D/YYYY] | no | date not stated |
| `prepared_date` | Prepared | date | Run date | [Month DD, YYYY] | yes | - |

### 2. Status Banner  (`status_banner`)

States plainly that no ownership figure is shown.

Fixed text:

> Unable to calculate
> The sources do not establish every input needed for a reliable ownership figure, so no ownership percentage, share count or valuation for this investor is shown. Supply the inputs below and rerun.

### 3. Required inputs  (`required_inputs`)

Each missing or conflicting input, with both conflicting values, their exact locations, and the CLI flag that resolves it.

Pattern:

```
{n}. {missing}
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `missing` | Missing input | list | resolve.Inputs.missing | [Input]: [why it is missing or conflicting, with values and locations]. Supply [--flag]. | yes | - |

- Numbered, one item per missing input, never empty in this variant.

### 4. Inputs that could be resolved  (`resolved_inputs`)

Inputs the sources did establish.

Columns: Input | Value | Source

Rows: One row per resolved input.

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | Input | text | resolve.ResolvedInput.name | [Input name] | yes | - |
| `value` | Value | text | Resolved value | [Value] | yes | - |
| `source` | Source | text | Workbook, tab and cell, deck slide and quoted label, or CLI flag | [File \| Location "quoted label"] | yes | - |

### 5. Top 3 data issues  (`top_issues`)

The three most material source problems: severity first, then materiality priority. INFO items never appear.

Pattern:

```
{n}. {title} [{severity}] - {evidence} Source: {sources}.
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `title` | Finding | text | validate.Issue.title (generated from the values found) | [Finding title] | yes | - |
| `severity` | Severity | text | HIGH / MEDIUM / LOW | HIGH\|MEDIUM\|LOW | yes | - |
| `evidence` | Evidence | text | Issue arithmetic, else detail | [Both values and the arithmetic] | yes | - |
| `sources` | Source | text | Up to four exact locations (Sheet!Cell, Slide N) | [Sheet!Cell; Slide N] | yes | - |

- Exactly three items when three or more non-INFO issues exist; fewer otherwise.
- Empty state: 'No material data issues found.'

### 6. Source facts (for reference only, not an ownership calculation)  (`source_facts`)

Source totals and tie-out, so the reader knows the cap table itself is readable.

Pattern:

```
Source pro forma: {source_outstanding} shares outstanding ({source_outstanding_ref}) and {source_fd} fully diluted ({source_fd_ref}); {tie_statement}. Full findings and the live-formula model are in the accompanying workbook.
```

| Field | Label | Format | Source | Placeholder | Required | Empty state |
| --- | --- | --- | --- | --- | --- | --- |
| `source_outstanding` | Source outstanding | shares | Cap table total shares outstanding | [NN,NNN,NNN.NN] | yes | - |
| `source_outstanding_ref` | Location | text | Sheet!Cell | [Sheet!Cell] | yes | - |
| `source_fd` | Source fully diluted | shares | Cap table fully diluted total | [NN,NNN,NNN.NN] | yes | - |
| `source_fd_ref` | Location | text | Sheet!Cell | [Sheet!Cell] | yes | - |
| `tie_statement` | Tie-out | text | Result of independent re-summing | [both tie to independent sums \| differences noted in the workbook] | yes | - |

### 7. Disclaimer  (`disclaimer`)

TEN standard disclaimer, required on investment-related documents.

Fixed text:

> Disclaimer: TEN is a "Funding as a Service" program. It is not a registered broker-dealer and does not offer investment advice or advise on the raising of capital through securities offerings. TEN does not recommend or otherwise suggest that any investor make an investment in a specific company, or that any company offer securities to a particular investor. TEN takes no part in the negotiation or execution of transactions for the purchase or sale of securities, and at no time has possession of funds or securities. No securities transactions are executed or negotiated on or through the TEN program. TEN receives no compensation in connection with the purchase or sale of securities.
