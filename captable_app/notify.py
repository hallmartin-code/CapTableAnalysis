"""Email delivery of finished analyses via Resend.

Email is a side channel, never the deliverable: every failure is reported and swallowed, so a
lost email never loses an analysis. The uploaded cap table and deck are never attached; only the
generated PDF, workbook and (when Claude ran) the AI review audit JSON are. The API key is never
echoed into notes or logs.

Settings (environment / Railway variables):
  RESEND_API_KEY  enables email when set
  RESEND_TO       comma-separated recipients (default Info@tencapital.group)
  RESEND_FROM     sender; its domain must be verified in Resend
  PUBLIC_BASE_URL optional link base for the results page (defaults to RAILWAY_PUBLIC_DOMAIN)
"""
from __future__ import annotations

import base64
import contextlib
import html
import os
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import httpx

from .fmt import pct, pp, sh, usd0

ENDPOINT = "https://api.resend.com/emails"
DEFAULT_TO = "Info@tencapital.group"
DEFAULT_FROM = "TEN Capital Ownership Calculator <ownership@tencapital.group>"
TIMEOUT_SECONDS = 30.0
MAX_ATTEMPTS = 3
MAX_ATTACH_MB = 35          # Resend's total message limit is 40 MB

INK, BODY, MUTED, CORAL = "#000000", "#4B4F58", "#7A7A7A", "#ED5644"
CREAM, GRAY, RULE = "#FFFDF6", "#F7F7F7", "#CBD6E2"


def resend_key() -> Optional[str]:
    return (os.environ.get("RESEND_API_KEY") or "").strip() or None


def recipients() -> list[str]:
    raw = (os.environ.get("RESEND_TO") or "").strip() or DEFAULT_TO
    return [r.strip() for r in raw.split(",") if r.strip()]


def sender() -> str:
    return (os.environ.get("RESEND_FROM") or "").strip() or DEFAULT_FROM


def is_configured() -> bool:
    return bool(resend_key()) and bool(recipients())


def results_url(job_id: Optional[str]) -> Optional[str]:
    if not job_id:
        return None
    base = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not base and os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        base = "https://" + os.environ["RAILWAY_PUBLIC_DOMAIN"].strip()
    return f"{base}/jobs/{job_id}" if base else None


@dataclass
class EmailResult:
    sent: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    to: list = field(default_factory=list)

    @property
    def note(self) -> str:
        return f"Results emailed to {', '.join(self.to)}." if self.sent else f"Email not sent: {self.error}"


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


# ------------------------------------------------------------------------------------ content

def subject(run) -> str:
    who = run.inputs.investor
    if run.status == "calculated":
        iv = run.result.investor_row
        return (f"Ownership: {run.company} {run.round_label} - {who} {pct(iv.pct_after_basic, 2)} basic / "
                f"{pct(iv.pct_after_fd, 2)} fully diluted")
    return f"Ownership: {run.company} {run.round_label} - unable to calculate ({len(run.missing)} input(s) needed)"


def _notes(run, url: Optional[str], ttl_minutes: Optional[float]) -> list[str]:
    notes = [f"{x.name}: {x.value if not isinstance(x.value, float) else f'{x.value:,.4f}' if x.value < 10 else f'{x.value:,.2f}'}"
             f" - {x.source}" for x in run.inputs.resolved]
    if url:
        notes.append(f"Results page: {url}" + (f" (expires {ttl_minutes:g} minutes after the run)" if ttl_minutes else ""))
    return notes


def build_html(run, url: Optional[str] = None, ttl_minutes: Optional[float] = None) -> str:
    def block(title, body):
        return (f'<div style="margin-top:22px;"><div style="font-size:14px;font-weight:700;color:{INK};'
                f'margin-bottom:8px;">{_e(title)}</div>{body}</div>') if body else ""

    td = f'style="padding:6px 6px;border-bottom:1px solid {RULE};font-size:12px;color:{BODY};text-align:right;"'
    tdl = td.replace("text-align:right", "text-align:left")
    if run.status == "calculated":
        res, iv, v = run.result, run.result.investor_row, run.result.valuation
        stats = [("Check size", usd0(run.inputs.check_size)), (f"New {run.round_label} shares", sh(res.new_shares)),
                 ("Basic ownership", pct(iv.pct_after_basic, 3)), ("Fully diluted", pct(iv.pct_after_fd, 3)),
                 ("Post-money", usd0(v["post_money"]))]
        cells = "".join(
            f'<td align="center" style="padding:10px 4px;border-right:1px solid {RULE};">'
            f'<div style="font-size:11px;font-weight:700;color:{INK};">{_e(k)}</div>'
            f'<div style="font-size:18px;font-weight:800;color:{CORAL if k == "Basic ownership" else INK};">{_e(val)}</div></td>'
            for k, val in stats)
        headline = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;'
                    f'background:{CREAM};border:1px solid {RULE};border-radius:8px;"><tr>{cells}</tr></table>')
        rows = "".join(f"<tr><td {tdl}>{_e(c.name)}</td><td {td}>{_e(sh(c.before, 0))}</td><td {td}>{_e(pct(c.pct_before_fd))}</td>"
                       f"<td {td}>{_e(sh(c.after, 0))}</td><td {td}>{_e(pct(c.pct_after_fd))}</td>"
                       f"<td {td}>{_e(pp(c.pct_after_fd - c.pct_before_fd, 3))}</td></tr>" for c in res.classes)
        th = f'style="padding:6px;background:{GRAY};font-size:11px;color:{INK};text-align:right;"'
        table = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
                 f'<th {th.replace("right", "left")}>Class</th><th {th}>Before sh.</th><th {th}>Before FD</th>'
                 f'<th {th}>After sh.</th><th {th}>After FD</th><th {th}>Change</th></tr>{rows}</table>')
        body = headline + block("Ownership by class: Before -> After", table)
        body += block("Post-money basis", f'<div style="font-size:12px;">Pre-money {_e(usd0(v["pre_money"]))} + proceeds '
                      f'{_e(usd0(v["proceeds"]))} = {_e(usd0(v["post_money"]))}. Implied at the share price: '
                      f'{_e(usd0(v["implied_post_basic"]))} on outstanding shares, {_e(usd0(v["implied_post_fd"]))} fully '
                      f'diluted.</div>')
    else:
        items = "".join(f'<li style="margin:0 0 6px;">{_e(m)}</li>' for m in run.missing)
        body = (f'<div style="margin-top:16px;padding:14px 16px;background:{GRAY};border-left:4px solid {CORAL};'
                f'border-radius:6px;"><div style="font-size:18px;font-weight:800;color:{CORAL};">Unable to calculate</div>'
                f'<div style="font-size:13px;margin-top:4px;">No ownership figure is shown. Required inputs:</div>'
                f'<ol style="margin:8px 0 0;padding-left:20px;font-size:13px;">{items}</ol></div>')
    issues = "".join(f'<li style="margin:0 0 8px;"><b style="color:{INK};">{_e(i.title)}</b> [{_e(i.severity)}]<br>'
                     f'{_e(i.arithmetic or i.detail[:300])}<br><span style="color:{MUTED};">Source: {_e("; ".join(i.refs[:4]))}'
                     f'</span></li>' for i in run.top_issues)
    body += block("Top data issues", f'<ol style="margin:0;padding-left:20px;font-size:13px;">{issues}</ol>' if issues else "")
    if run.ai is not None and not run.ai_error:
        body += block("Claude review", f'<div style="font-size:13px;">{_e(run.ai.summary)}</div>'
                      f'<div style="font-size:12px;color:{MUTED};margin-top:6px;">{len(run.ai.findings)} verified finding(s), '
                      f'{len(run.ai.discarded)} discarded, {len(run.ai.image_figures)} figure(s) read from slide images. '
                      f'AI findings never change a calculated figure.</div>')
    elif run.ai_error:
        body += block("Claude review", f'<div style="font-size:12px;color:{MUTED};">{_e(run.ai_error)}</div>')
    notes = "".join(f'<li style="margin:0 0 4px;">{_e(n)}</li>' for n in _notes(run, url, ttl_minutes))
    body += block("Inputs and run notes", f'<ul style="margin:0;padding-left:20px;font-size:12px;color:{MUTED};">{notes}</ul>')

    return f"""<!doctype html><html><body style="margin:0;padding:0;background:{CREAM};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};padding:24px 12px;"><tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff;border:1px solid {RULE};
 border-radius:10px;font-family:Inter,Arial,Helvetica,sans-serif;color:{BODY};"><tr><td style="padding:28px 30px;">
 <div style="font-size:12px;font-weight:600;color:{CORAL};">TEN Capital Network &middot; Investor ownership analysis</div>
 <h1 style="margin:8px 0 4px;font-size:24px;font-weight:800;color:{INK};line-height:1.2;">{_e(run.company)} &ndash; {_e(run.round_label)}</h1>
 <div style="font-size:13px;color:{MUTED};">Investor: {_e(run.inputs.investor)} &middot; {_e(f"{date.today():%B %d, %Y}")}</div>
 {body}
 <div style="margin-top:24px;padding-top:14px;border-top:1px solid {RULE};font-size:12px;color:{MUTED};line-height:1.6;">
  Attached: the one-page ownership summary (PDF) and the live-formula workbook (Excel){" and the Claude review audit (JSON)" if run.ai is not None and getattr(run.ai, "raw", None) else ""}.<br>
  Automated analysis of the supplied cap table and deck. Deck statements are company claims, not independent
  verification. Not investment advice.</div>
</td></tr></table></td></tr></table></body></html>"""


def build_text(run, url: Optional[str] = None, ttl_minutes: Optional[float] = None) -> str:
    lines = [f"Investor ownership analysis: {run.company} - {run.round_label}", f"Investor: {run.inputs.investor}", ""]
    if run.status == "calculated":
        res, iv, v = run.result, run.result.investor_row, run.result.valuation
        lines += [f"Check size: {usd0(run.inputs.check_size)}", f"New shares: {sh(res.new_shares)}",
                  f"Basic ownership: {pct(iv.pct_after_basic, 3)}", f"Fully diluted ownership: {pct(iv.pct_after_fd, 3)}",
                  f"Post-money: {usd0(v['post_money'])}", "", "By class (before -> after shares, after FD %):"]
        lines += [f"  {c.name}: {sh(c.before, 0)} -> {sh(c.after, 0)} ({pct(c.pct_after_fd)}, "
                  f"{pp(c.pct_after_fd - c.pct_before_fd, 3)})" for c in res.classes]
    else:
        lines += ["UNABLE TO CALCULATE - required inputs:"] + [f"  - {m}" for m in run.missing]
    if run.top_issues:
        lines += ["", "Top data issues:"] + [f"  {n}. [{i.severity}] {i.title} (Source: {'; '.join(i.refs[:4])})"
                                             for n, i in enumerate(run.top_issues, 1)]
    if run.ai is not None and not run.ai_error:
        lines += ["", f"Claude review: {run.ai.summary}"]
    lines += ["", "Inputs and run notes:"] + [f"  - {n}" for n in _notes(run, url, ttl_minutes)]
    lines += ["", "Attached: ownership summary PDF and Excel workbook. Not investment advice."]
    return "\n".join(lines)


def failure_subject(company_hint: str) -> str:
    return f"Ownership analysis failed: {company_hint}"


# ------------------------------------------------------------------------------------ sending

def _post(payload: dict, post) -> EmailResult:
    key, to = resend_key(), payload["to"]
    delay, last = 2.0, "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = post(ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as exc:
            last = f"could not reach Resend ({type(exc).__name__})"
        else:
            if resp.status_code < 300:
                mid = None
                with contextlib.suppress(ValueError):
                    mid = resp.json().get("id")
                return EmailResult(True, message_id=mid, to=to)
            last = _describe(resp)
            if resp.status_code < 500 and resp.status_code != 429:
                break  # a rejected request will not succeed on retry
        if attempt < MAX_ATTEMPTS:
            time.sleep(delay)
            delay *= 2
    return EmailResult(False, error=last, to=to)


def send_results(run, job_id: Optional[str] = None, ttl_minutes: Optional[float] = None, post=None) -> EmailResult:
    """Email a finished analysis (calculated or blocked). Returns a result; never raises."""
    post = post or httpx.post
    if not resend_key():
        return EmailResult(False, error="RESEND_API_KEY is not set")
    try:
        url = results_url(job_id)
        files = [run.pdf, run.xlsx]
        ai_json = os.path.splitext(run.xlsx)[0] + "_ai_review.json"
        if os.path.exists(ai_json):
            files.append(ai_json)
        attachments, total = [], 0
        for path in files:
            data = open(path, "rb").read()
            total += len(data)
            if total > MAX_ATTACH_MB * 1024 * 1024:
                break
            attachments.append({"filename": os.path.basename(path), "content": base64.b64encode(data).decode()})
        payload = {"from": sender(), "to": recipients(), "subject": subject(run),
                   "html": build_html(run, url, ttl_minutes), "text": build_text(run, url, ttl_minutes),
                   "attachments": attachments}
    except Exception as exc:  # building the email must never break the run
        return EmailResult(False, error=f"could not build the email ({type(exc).__name__}: {exc})", to=recipients())
    return _post(payload, post)


def send_failure(error: str, cap_name: str, deck_name: str, job_id: Optional[str] = None, post=None) -> EmailResult:
    """Short notice when an analysis crashes, so a failed run is not silently lost."""
    post = post or httpx.post
    if not resend_key():
        return EmailResult(False, error="RESEND_API_KEY is not set")
    text = (f"An ownership analysis could not be completed.\n\nCap table: {cap_name}\nDeck: {deck_name}\n"
            f"Error: {error}\n" + (f"Job: {results_url(job_id)}\n" if results_url(job_id) else ""))
    payload = {"from": sender(), "to": recipients(), "subject": failure_subject(cap_name), "text": text,
               "html": f"<pre style='font-family:Arial,sans-serif;font-size:13px'>{_e(text)}</pre>"}
    return _post(payload, post)


def _describe(resp) -> str:
    try:
        body = resp.json()
        detail = body.get("message") or body.get("error") or str(body)
    except ValueError:
        detail = (resp.text or "").strip()[:200]
    return f"Resend returned {resp.status_code}: {detail}"
