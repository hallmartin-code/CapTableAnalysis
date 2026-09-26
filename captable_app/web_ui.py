"""HTML for the web app, following the TEN Capital "Deck Analyzer" dark UI design.

Pure rendering: every function returns an HTML string; all dynamic text is escaped with _e().
"""
from __future__ import annotations

import html
import json
from typing import Optional

from .fmt import pct, pp, sh, usd0

STEPS = [
    ("Reading cap table and deck", "Reading the cap table and deck"),
    ("Running source checks", "Checking formulas, totals and deck vs cap table"),
    ("Claude is reviewing", "Claude reviews the sources and image-only slides"),
    ("Resolving inputs", "Resolving inputs and calculating ownership"),
    ("Writing workbook", "Writing the workbook and one-page PDF"),
    ("Verifying", "Verifying outputs"),
    ("Emailing results", "Emailing the results"),
]


CLI_TO_FORM = [
    ("--commitments-in-before yes|no (with 'no', also --uncounted-commitments USD)",
     "'Round commitments already in the cap table?' under Advanced inputs (with No, also 'Commitments not in the cap table')"),
    ("--uncounted-commitments", "'Commitments not in the cap table'"),
    ("--commitments-in-before no", "'Round commitments already in the cap table?' = No"),
    ("Supply --check-size", "Enter a Check size"),
    ("supply --share-price", "enter a Share price under Advanced inputs"),
    ("supply --pre-money", "enter a Pre-money valuation under Advanced inputs"),
    ("--check-size", "Check size"),
]


def web_wording(msg: str) -> str:
    """Missing-input messages name CLI flags; on the web, name the form fields instead."""
    for a, b in CLI_TO_FORM:
        msg = msg.replace(a, b)
    return msg


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


CSS = """
:root{
  --navy-950:#0B1526; --navy-900:#101E33; --navy-800:#16283F; --navy-700:#1E354F;
  --coral:#EE5A4E; --coral-soft:#F0776C; --amber:#F3A22A; --teal:#35BEBB;
  --ink-100:#F3F6FA; --ink-300:#C4D0E0; --ink-500:#7E90A8; --ink-600:#5C6E86;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--navy-950);color:var(--ink-100);font-family:'Inter',system-ui,sans-serif;min-height:100vh}
body{display:flex;justify-content:center;padding:40px 16px 48px;position:relative;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(480px 380px at 14% 8%,rgba(238,90,78,.16),transparent 60%),
             radial-gradient(480px 380px at 86% 6%,rgba(243,162,42,.13),transparent 60%),
             radial-gradient(560px 420px at 50% 100%,rgba(53,190,187,.14),transparent 60%)}
.stage{position:relative;z-index:1;width:100%;max-width:720px}
.stage.wide{max-width:1000px}
a{color:var(--teal)}
:focus-visible{outline:2px solid var(--teal);outline-offset:2px}

/* brand lockup: the real logo on a light chip (its wordmark is black) */
.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:24px;padding:0 4px}
.brand{display:flex;align-items:center;gap:12px;text-decoration:none}
.brand-chip{background:#FFFDF6;border-radius:10px;padding:6px 10px;display:flex;box-shadow:0 6px 18px -8px rgba(0,0,0,.6)}
.brand-chip img{height:30px;width:auto;display:block}
.brand-app{font-family:'Sora',sans-serif;font-weight:700;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-300)}
.nav{font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-500);text-decoration:none;
  border:1px solid var(--navy-700);border-radius:8px;padding:7px 10px}
.nav:hover{color:var(--ink-100);border-color:var(--teal)}

.card{background:linear-gradient(180deg,var(--navy-900) 0%,var(--navy-800) 100%);border:1px solid var(--navy-700);border-radius:20px;
  padding:40px 40px 32px;box-shadow:0 30px 60px -20px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.03);position:relative;overflow:hidden;margin-bottom:18px}
.card::after{content:"";position:absolute;top:-2px;left:40px;right:40px;height:2px;background:linear-gradient(90deg,var(--coral),var(--amber),var(--teal));border-radius:2px}
.card.plain::after{display:none}
.card.plain{padding:26px 28px}
.eyebrow{display:flex;align-items:center;gap:8px;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--teal);margin-bottom:14px}
.eyebrow::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px rgba(53,190,187,.18)}
.eyebrow.bad{color:var(--coral)} .eyebrow.bad::before{box-shadow:0 0 0 3px rgba(238,90,78,.2)}
h1{font-family:'Sora',sans-serif;font-size:28px;font-weight:700;line-height:1.25;margin:0 0 12px;letter-spacing:-.01em}
h1 .arrow{color:var(--ink-500);font-weight:400;margin:0 4px}
.grad{color:var(--coral-soft);background:linear-gradient(90deg,var(--coral-soft),var(--amber));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
h2{font-family:'Sora',sans-serif;font-size:16px;font-weight:600;margin:0 0 14px;color:var(--ink-100)}
.lede{color:var(--ink-300);font-size:15px;line-height:1.6;margin:0 0 28px;max-width:52ch}
.sub{color:var(--ink-500);font-size:13px;margin:-4px 0 0}
.muted{color:var(--ink-500);font-size:12.5px;line-height:1.6}

/* dropzones */
.drops{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.dropzone{position:relative;display:block;border:1.5px dashed var(--navy-700);border-radius:14px;padding:26px 18px;text-align:center;cursor:pointer;
  background:rgba(255,255,255,.015);transition:border-color .18s,background .18s,transform .18s}
.dropzone:hover,.dropzone.drag{border-color:var(--teal);background:rgba(53,190,187,.05)}
.dropzone.ok{border-style:solid;border-color:rgba(53,190,187,.55);background:rgba(53,190,187,.06)}
.dropzone.err{border-color:var(--coral)}
.dropzone:focus-within{outline:2px solid var(--teal);outline-offset:2px}
.dz-icon{width:38px;height:38px;margin:0 auto 12px;border-radius:10px;background:linear-gradient(135deg,rgba(238,90,78,.16),rgba(243,162,42,.16));
  border:1px solid var(--navy-700);display:flex;align-items:center;justify-content:center}
.dz-icon svg{width:18px;height:18px}
.dz-label{font-family:'JetBrains Mono',monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-500);margin-bottom:6px}
.dz-title{font-size:15px;font-weight:600;color:var(--ink-100);margin-bottom:6px;word-break:break-word}
.dz-sub{font-family:'JetBrains Mono',monospace;font-size:11.5px;color:var(--ink-500)}
.dz-sub b{color:var(--ink-300);font-weight:500}
.file-input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}

/* fields */
.fields{display:grid;grid-template-columns:1fr 1fr;gap:14px 16px;margin-top:22px}
.field label{display:block;font-size:12.5px;font-weight:600;color:var(--ink-300);margin-bottom:6px}
.field .hint{display:block;font-weight:400;color:var(--ink-500);font-size:11.5px;margin-top:5px}
.input,select{width:100%;background:var(--navy-950);border:1px solid var(--navy-700);border-radius:10px;color:var(--ink-100);
  font:500 14px 'Inter',sans-serif;padding:11px 12px;transition:border-color .15s}
.input::placeholder{color:var(--ink-600)}
.input:focus,select:focus{border-color:var(--teal);outline:none;box-shadow:0 0 0 3px rgba(53,190,187,.15)}
.money{position:relative}
.money::before{content:"$";position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--ink-500);font-size:14px}
.money .input{padding-left:24px}
details.more{margin-top:18px;border:1px solid var(--navy-700);border-radius:12px;background:rgba(255,255,255,.012)}
details.more summary{cursor:pointer;list-style:none;padding:13px 16px;font-size:13px;font-weight:600;color:var(--ink-300);display:flex;justify-content:space-between}
details.more summary::-webkit-details-marker{display:none}
details.more summary::after{content:"+";font-family:'JetBrains Mono',monospace;color:var(--ink-500)}
details.more[open] summary::after{content:"\\2212"}
details.more .fields{margin:0;padding:4px 16px 16px}

/* AI switch */
.switch{display:flex;gap:14px;align-items:flex-start;margin-top:18px;padding:14px 16px;border:1px solid var(--navy-700);border-radius:12px;cursor:pointer}
.switch input{position:absolute;opacity:0;width:1px;height:1px}
.track{flex-shrink:0;width:40px;height:22px;border-radius:999px;background:var(--navy-700);position:relative;transition:background .18s;margin-top:1px}
.track::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:var(--ink-300);transition:transform .18s,background .18s}
.switch input:checked + .track{background:linear-gradient(90deg,var(--teal),#4FC4D6)}
.switch input:checked + .track::after{transform:translateX(18px);background:#fff}
.switch input:focus-visible + .track{outline:2px solid var(--teal);outline-offset:2px}
.switch b{display:block;font-size:14px;color:var(--ink-100);margin-bottom:3px}
.switch span.desc{font-size:12.5px;color:var(--ink-500);line-height:1.5}

/* CTA + buttons */
.cta{width:100%;margin-top:22px;padding:16px 20px;border:none;border-radius:12px;background:linear-gradient(90deg,var(--coral) 0%,var(--coral-soft) 45%,var(--amber) 100%);
  color:#17130E;font-family:'Sora',sans-serif;font-weight:700;font-size:15px;letter-spacing:.01em;cursor:pointer;transition:filter .15s,transform .15s;
  box-shadow:0 10px 24px -10px rgba(238,90,78,.45)}
.cta:hover{filter:brightness(1.06);transform:translateY(-1px)}
.cta:disabled{filter:grayscale(.5) brightness(.8);cursor:progress;transform:none}
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 16px;border-radius:10px;font-family:'Sora',sans-serif;font-weight:600;font-size:13.5px;text-decoration:none;
  border:1px solid var(--navy-700);color:var(--ink-100);background:rgba(255,255,255,.02)}
.btn:hover{border-color:var(--teal)}
.btn.primary{border:none;color:#17130E;background:linear-gradient(90deg,var(--coral),var(--coral-soft) 45%,var(--amber))}
.btns{display:flex;flex-wrap:wrap;gap:10px}

/* upload progress */
.progress{display:none;margin-top:16px}
.progress.on{display:block}
.bar{height:6px;border-radius:999px;background:var(--navy-700);overflow:hidden}
.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--coral),var(--amber),var(--teal));transition:width .2s}
.progress .muted{margin-top:8px;font-family:'JetBrains Mono',monospace;font-size:11.5px}
.alert{display:none;margin-top:14px;padding:12px 14px;border-radius:10px;border:1px solid rgba(238,90,78,.5);background:rgba(238,90,78,.08);color:#FFD9D5;font-size:13px}
.alert.on{display:block}

.disclosure{margin-top:22px;padding-top:18px;border-top:1px solid var(--navy-700);font-size:12px;line-height:1.6;color:var(--ink-500)}
code{font-family:'JetBrains Mono',monospace;background:var(--navy-950);border:1px solid var(--navy-700);color:var(--ink-300);padding:2px 6px;border-radius:5px;font-size:11.5px}
footer{text-align:center;margin-top:22px;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.08em;color:var(--ink-600);text-transform:uppercase}

/* running steps */
.steps{list-style:none;margin:6px 0 0;padding:0}
.steps li{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid rgba(30,53,79,.7);font-size:14px;color:var(--ink-500)}
.steps li:last-child{border-bottom:none}
.dot{flex-shrink:0;width:18px;height:18px;border-radius:50%;border:1.5px solid var(--navy-700);display:flex;align-items:center;justify-content:center}
.steps li.done{color:var(--ink-300)} .steps li.done .dot{background:var(--teal);border-color:var(--teal)}
.steps li.done .dot::after{content:"";width:7px;height:4px;border-left:2px solid var(--navy-950);border-bottom:2px solid var(--navy-950);transform:rotate(-45deg) translate(1px,-1px)}
.steps li.now{color:var(--ink-100);font-weight:600} .steps li.now .dot{border-color:var(--amber);border-top-color:transparent;animation:spin .9s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

/* results */
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:22px}
.stat{background:var(--navy-950);border:1px solid var(--navy-700);border-radius:14px;padding:14px 14px 12px}
.stat span{display:block;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-500);margin-bottom:8px}
.stat b{font-family:'Sora',sans-serif;font-size:21px;font-weight:700;color:var(--ink-100);font-variant-numeric:tabular-nums;word-break:break-word}
.stat.hero{border-color:rgba(238,90,78,.45);background:linear-gradient(180deg,rgba(238,90,78,.10),rgba(243,162,42,.04))}
.stat.hero b{font-size:25px}
.table-wrap{overflow-x:auto;margin:0 -4px}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:620px}
th{font-family:'JetBrains Mono',monospace;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-500);font-weight:500;text-align:right;padding:8px 10px;border-bottom:1px solid var(--navy-700)}
td{padding:9px 10px;text-align:right;border-bottom:1px solid rgba(30,53,79,.7);color:var(--ink-300);font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}
tr.total td{color:var(--ink-100);font-weight:600;border-top:1px solid var(--navy-700)}
tr.inv td{color:var(--ink-100);font-weight:600;background:rgba(238,90,78,.08)}
td.neg{color:var(--coral-soft)} td.pos{color:var(--teal)}
.issues{list-style:none;margin:0;padding:0;counter-reset:i}
.issues li{padding:14px 0;border-bottom:1px solid rgba(30,53,79,.7)}
.issues li:last-child{border-bottom:none}
.issues .t{font-weight:600;color:var(--ink-100);font-size:14px;margin:6px 0 4px}
.issues .d{color:var(--ink-300);font-size:13px;line-height:1.55}
.issues .s{color:var(--ink-500);font-family:'JetBrains Mono',monospace;font-size:11px;margin-top:6px}
.pill{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:.1em;padding:3px 8px;border-radius:999px;border:1px solid}
.pill.HIGH{color:var(--coral-soft);border-color:rgba(238,90,78,.5);background:rgba(238,90,78,.08)}
.pill.MEDIUM{color:var(--amber);border-color:rgba(243,162,42,.5);background:rgba(243,162,42,.08)}
.pill.LOW,.pill.INFO{color:var(--ink-300);border-color:var(--navy-700)}
.blocked{border:1px solid rgba(238,90,78,.45);background:rgba(238,90,78,.07);border-radius:14px;padding:18px 20px;margin-top:22px}
.blocked ol{margin:10px 0 0;padding-left:20px;color:var(--ink-300);font-size:13.5px;line-height:1.55}
.blocked li{margin:0 0 8px}
.note{display:flex;gap:10px;align-items:flex-start;font-size:12.5px;color:var(--ink-300);margin-top:16px}
.note::before{content:"";flex-shrink:0;width:6px;height:6px;margin-top:6px;border-radius:50%;background:var(--teal)}
.note.bad::before{background:var(--coral)}

@media (max-width:820px){.stats{grid-template-columns:repeat(2,1fr)} .stat.hero{grid-column:1 / -1}}
@media (max-width:600px){
  body{padding:24px 12px 36px}
  .card{padding:30px 20px 24px} .card::after{left:20px;right:20px} .card.plain{padding:22px 18px}
  h1{font-size:23px}
  .drops,.fields{grid-template-columns:1fr}
  .brand-app{display:none}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

FILE_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="#F3F6FA" stroke-width="1.6" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><path d="M14 3v4a1 1 0 0 0 1 1h4"/>'
             '<path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2Z"/></svg>')
GRID_ICON = ('<svg viewBox="0 0 24 24" fill="none" stroke="#F3F6FA" stroke-width="1.6" stroke-linecap="round" '
             'stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/>'
             '<path d="M3 10h18M3 15h18M9 4v16"/></svg>')

FORM_JS = """
(function(){
  const MAX = window.MAX_UPLOAD_MB * 1024 * 1024;
  function fmt(n){ return n > 1048576 ? (n/1048576).toFixed(1)+' MB' : Math.max(1, Math.round(n/1024))+' KB'; }
  document.querySelectorAll('.dropzone').forEach(function(z){
    const input = z.querySelector('input[type=file]');
    const title = z.querySelector('.dz-title'), sub = z.querySelector('.dz-sub');
    const t0 = title.innerHTML, s0 = sub.innerHTML;
    const exts = input.accept.split(',');
    function show(){
      const f = input.files[0];
      z.classList.remove('ok','err');
      if(!f){ title.innerHTML = t0; sub.innerHTML = s0; return; }
      const ext = '.' + f.name.split('.').pop().toLowerCase();
      if(exts.indexOf(ext) < 0){ z.classList.add('err'); title.textContent = f.name; sub.textContent = 'Expected ' + exts.join(' or '); return; }
      if(f.size > MAX){ z.classList.add('err'); title.textContent = f.name; sub.textContent = 'Larger than ' + window.MAX_UPLOAD_MB + ' MB'; return; }
      z.classList.add('ok'); title.textContent = f.name; sub.textContent = fmt(f.size) + ' \\u00b7 ready';
    }
    input.addEventListener('change', show);
    ['dragenter','dragover'].forEach(function(ev){ z.addEventListener(ev, function(e){ e.preventDefault(); z.classList.add('drag'); }); });
    ['dragleave','drop'].forEach(function(ev){ z.addEventListener(ev, function(){ z.classList.remove('drag'); }); });
    z.addEventListener('drop', function(e){ e.preventDefault(); if(e.dataTransfer.files.length){ input.files = e.dataTransfer.files; show(); } });
  });
  document.querySelectorAll('form[data-xhr]').forEach(function(form){
    form.addEventListener('submit', function(e){
      if(form.querySelector('.dropzone.err')){ e.preventDefault(); return; }
      e.preventDefault();
      const btn = form.querySelector('.cta'), prog = form.querySelector('.progress'), bar = prog.querySelector('i'),
            label = prog.querySelector('.muted'), alert = form.querySelector('.alert');
      btn.disabled = true; btn.textContent = 'Uploading\\u2026'; prog.classList.add('on'); alert.classList.remove('on');
      const xhr = new XMLHttpRequest();
      xhr.open('POST', form.action);
      xhr.upload.onprogress = function(ev){
        if(ev.lengthComputable){ const p = Math.round(ev.loaded / ev.total * 100); bar.style.width = p + '%';
          label.textContent = 'Uploading ' + fmt(ev.loaded) + ' of ' + fmt(ev.total) + ' \\u00b7 ' + p + '%'; }
      };
      xhr.upload.onload = function(){ label.textContent = 'Upload complete \\u00b7 starting analysis\\u2026'; };
      xhr.onload = function(){
        if(xhr.status < 400 && xhr.responseURL){ window.location = xhr.responseURL; return; }
        let msg = 'The server rejected the request (' + xhr.status + ').';
        try { const d = JSON.parse(xhr.responseText); if(d.detail) msg = d.detail; } catch(_){}
        alert.textContent = msg; alert.classList.add('on'); btn.disabled = false; btn.textContent = btn.dataset.label;
        prog.classList.remove('on'); bar.style.width = '0';
      };
      xhr.onerror = function(){ alert.textContent = 'Network error - the upload did not complete. Please try again.';
        alert.classList.add('on'); btn.disabled = false; btn.textContent = btn.dataset.label; prog.classList.remove('on'); };
      xhr.send(new FormData(form));
    });
  });
})();
"""


def page(title: str, body: str, wide: bool = False, script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><title>{_e(title)} &middot; TEN Capital Network</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" type="image/png" sizes="32x32" href="/public/favicon-32x32.png">
<link rel="icon" type="image/png" sizes="236x236" href="/public/icon.png">
<link rel="apple-touch-icon" sizes="180x180" href="/public/apple-touch-icon.png">
<meta name="theme-color" content="#0B1526">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body><div class="stage{' wide' if wide else ''}">
<div class="topbar">
  <a class="brand" href="/" aria-label="New analysis"><span class="brand-chip"><img src="/static/logo.png" alt="TEN Capital Network"></span>
  <span class="brand-app">Ownership Analyzer</span></a>
  <a class="nav" href="/">+ New analysis</a>
</div>
{body}
<footer>Powered by TEN Capital Network</footer>
</div>{f"<script>{script}</script>" if script else ""}</body></html>"""


def _val(p: dict, k: str) -> str:
    x = p.get(k)
    return "" if x is None else _e(f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else x)


def _sel(p: dict, k: str, v: str) -> str:
    return " selected" if (p.get(k) or "") == v else ""


def form_fields(prev: Optional[dict], ai_available: bool, ai_default: bool, open_advanced: bool = False) -> str:
    p = prev or {}
    ai_on = ai_default if prev is None else bool(p.get("ai_review"))
    ai = (f"""<label class="switch"><input type="checkbox" name="ai_review" value="1"{" checked" if ai_on else ""}>
<span class="track" aria-hidden="true"></span><span><b>Claude AI review</b><span class="desc">Reads image-only slides and looks for
source problems the rule-based checks miss. Every AI finding must quote the source verbatim; AI never changes a calculated figure.</span></span></label>"""
          if ai_available else '<p class="muted">Claude AI review is unavailable: ANTHROPIC_API_KEY is not set on the server.</p>')
    return f"""
<div class="fields">
  <div class="field"><label for="investor">Investor name</label>
    <input class="input" id="investor" name="investor" value="{_val(p, 'investor')}" placeholder="New investor" maxlength="80"></div>
  <div class="field"><label for="check_size">Check size</label>
    <div class="money"><input class="input" id="check_size" name="check_size" inputmode="decimal" value="{_val(p, 'check_size')}" placeholder="e.g. 250,000"></div>
    <span class="hint">Blank = full open allocation, only if the sources state it unambiguously.</span></div>
</div>
<details class="more"{" open" if open_advanced else ""}><summary>Advanced inputs</summary>
<div class="fields">
  <div class="field"><label for="share_price">Share price</label>
    <div class="money"><input class="input" id="share_price" name="share_price" inputmode="decimal" value="{_val(p, 'share_price')}" placeholder="Cap-table issue price"></div></div>
  <div class="field"><label for="pre_money">Pre-money valuation</label>
    <div class="money"><input class="input" id="pre_money" name="pre_money" inputmode="decimal" value="{_val(p, 'pre_money')}" placeholder="From the deck"></div></div>
  <div class="field"><label for="cib">Round commitments already in the cap table?</label>
    <select id="cib" name="commitments_in_before"><option value=""{_sel(p, 'commitments_in_before', '')}>Let the sources decide</option>
    <option value="yes"{_sel(p, 'commitments_in_before', 'yes')}>Yes</option><option value="no"{_sel(p, 'commitments_in_before', 'no')}>No</option></select></div>
  <div class="field"><label for="unc">Commitments not in the cap table</label>
    <div class="money"><input class="input" id="unc" name="uncounted_commitments" inputmode="decimal" value="{_val(p, 'uncounted_commitments')}" placeholder="Only when the answer is No"></div></div>
  <div class="field"><label for="ph">Unsold "remaining round" plug row</label>
    <select id="ph" name="placeholder"><option value="release"{_sel(p, 'placeholder_mode', 'release')}>Release it in After (default)</option>
    <option value="keep"{_sel(p, 'placeholder_mode', 'keep')}>Keep it</option></select></div>
</div></details>
{ai}"""


def _submit(label: str) -> str:
    return f"""<button class="cta" type="submit" data-label="{_e(label)}">{_e(label)}</button>
<div class="progress" aria-live="polite"><div class="bar"><i></i></div><div class="muted"></div></div>
<div class="alert" role="alert"></div>"""


def _disclosure(ai_available: bool, email_to: Optional[list[str]], ttl: float) -> str:
    parts = ["Files are processed on the server"]
    if ai_available:
        parts.append("with the Claude review on, the extracted content and image-only slides are sent to Anthropic's Claude API")
    text = "; ".join(parts) + "."
    if email_to:
        text += " A copy of every result (PDF and workbook) is emailed to " + ", ".join(f"<code>{_e(t)}</code>" for t in email_to) + "."
    text += f" Uploads and results are deleted {ttl:g} minutes after each run."
    return f'<div class="disclosure">{text}</div>'


def index_page(ai_available: bool, ai_default: bool, email_to: Optional[list[str]], ttl: float, max_mb: float) -> str:
    body = f"""
<div class="card">
  <div class="eyebrow">Ownership Analyzer</div>
  <h1>Cap Table + Deck<span class="arrow">&rarr;</span><span class="grad">Investor Ownership</span></h1>
  <p class="lede">Upload the pro forma cap table and the pitch deck. Get basic and fully diluted ownership, a live-formula
  workbook and a one-page PDF, with every figure traced to its source.</p>
  <form method="post" action="/analyze" enctype="multipart/form-data" data-xhr>
    <div class="drops">
      <label class="dropzone"><div class="dz-icon">{GRID_ICON}</div><div class="dz-label">Pro forma cap table</div>
        <div class="dz-title">Choose or drop the cap table</div><div class="dz-sub"><b>.xlsx</b></div>
        <input class="file-input" type="file" name="cap_table" accept=".xlsx" required aria-label="Pro forma cap table (.xlsx)"></label>
      <label class="dropzone"><div class="dz-icon">{FILE_ICON}</div><div class="dz-label">Pitch deck</div>
        <div class="dz-title">Choose or drop the deck</div><div class="dz-sub"><b>.pptx</b> &middot; <b>.pdf</b> &nbsp;&middot;&nbsp; up to {max_mb:g}&nbsp;MB</div>
        <input class="file-input" type="file" name="deck" accept=".pptx,.pdf" required aria-label="Pitch deck (.pptx or .pdf)"></label>
    </div>
    {form_fields(None, ai_available, ai_default)}
    {_submit("Run ownership analysis")}
  </form>
  {_disclosure(ai_available, email_to, ttl)}
</div>"""
    return page("Ownership Analyzer", body, script=f"window.MAX_UPLOAD_MB={max_mb:g};" + FORM_JS)


def running_page(job_id: str, progress: list[str], ai: bool, email: bool) -> str:
    steps = [s for s in STEPS if (ai or not s[0].startswith("Claude")) and (email or s[0] != "Emailing results")
             and s[0] != "Verifying"]
    items = "".join(f'<li data-key="{_e(k)}"><span class="dot"></span>{_e(label)}</li>' for k, label in steps)
    body = f"""
<div class="card">
  <div class="eyebrow">Analysis running</div>
  <h1>Analyzing your documents</h1>
  <p class="lede">This page updates automatically.{" The Claude review usually takes one to three minutes." if ai else ""}</p>
  <ul class="steps" id="steps">{items}</ul>
</div>"""
    script = f"""
(function(){{
  const keys = Array.from(document.querySelectorAll('#steps li')).map(li => li.dataset.key);
  function paint(log){{
    let idx = -1;
    log.forEach(m => {{ keys.forEach((k, i) => {{ if (m.indexOf(k) === 0) idx = Math.max(idx, i); }}); }});
    document.querySelectorAll('#steps li').forEach((li, i) => {{
      li.className = i < idx ? 'done' : (i === idx ? 'now' : '');
    }});
  }}
  paint({json.dumps(progress)});
  setInterval(async () => {{
    try {{
      const r = await fetch('/jobs/{job_id}/status'); const d = await r.json();
      paint(d.log || d.progress);
      if (d.status === 'done' || d.status === 'error') location.reload();
    }} catch (_) {{}}
  }}, 2000);
}})();"""
    return page("Analysis running", body, script=script)


def error_page(error: str, email_note: Optional[str]) -> str:
    body = f"""
<div class="card">
  <div class="eyebrow bad">Analysis failed</div>
  <h1>The analysis could not be completed</h1>
  <p class="lede">Check that the cap table is a stakeholder-level pro forma export (.xlsx) and the deck is a .pptx or .pdf.</p>
  <p class="muted"><code>{_e(error)}</code></p>
  {f'<div class="note">{_e(email_note)}</div>' if email_note else ''}
  <div class="btns" style="margin-top:20px"><a class="btn primary" href="/">Start a new analysis</a></div>
</div>"""
    return page("Analysis failed", body)


def result_page(job_id: str, r, params: dict, email_note: Optional[str], ttl: float,
                ai_available: bool, ai_default: bool) -> str:
    calc = r.status == "calculated"
    head = f"""
<div class="card">
  <div class="eyebrow{'' if calc else ' bad'}">{'Ownership calculated' if calc else 'Unable to calculate'}</div>
  <h1>{_e(r.company)} <span class="arrow">&middot;</span> <span class="grad">{_e(r.round_label)}</span></h1>
  <p class="sub">Investor: {_e(r.inputs.investor)}</p>"""
    if calc:
        res, iv, v = r.result, r.result.investor_row, r.result.valuation
        tiles = [("Check size", usd0(r.inputs.check_size), ""), (f"New {r.round_label} shares", sh(res.new_shares), ""),
                 ("Basic ownership", pct(iv.pct_after_basic, 3), "hero"),
                 ("Fully diluted", pct(iv.pct_after_fd, 3), ""), ("Post-money", usd0(v["post_money"]), "")]
        head += '<div class="stats">' + "".join(
            f'<div class="stat {c}"><span>{_e(k)}</span><b{" class=grad" if c else ""}>{_e(val)}</b></div>'
            for k, val, c in tiles) + "</div>"
    else:
        head += ('<div class="blocked"><b>No ownership figure is shown.</b> The sources do not establish every input '
                 'needed. Add the inputs below and run again; the uploaded files are reused.<ol>'
                 + "".join(f"<li>{_e(web_wording(m))}</li>" for m in r.missing) + "</ol></div>")
    has_ai_json = r.ai is not None and getattr(r.ai, "raw", None)
    head += f"""
  <div class="btns" style="margin-top:22px">
    <a class="btn primary" href="/jobs/{job_id}/download/pdf">Download PDF summary</a>
    <a class="btn" href="/jobs/{job_id}/download/xlsx">Download Excel workbook</a>
    {f'<a class="btn" href="/jobs/{job_id}/download/ai">Claude review audit (JSON)</a>' if has_ai_json else ''}
  </div>
  {f'<div class="note{"" if email_note.startswith("Results emailed") else " bad"}">{_e(email_note)}</div>' if email_note else ''}
  <div class="note">Files are deleted {ttl:g} minutes after the run.</div>
</div>"""
    parts = [head]
    if calc:
        def cls(x):
            r = round(x * 100, 3)          # colour follows the displayed (rounded) pp value
            return "neg" if r < 0 else ("pos" if r > 0 else "")
        rows = "".join(
            f'<tr><td>{_e(c.name)}</td><td>{_e(sh(c.before, 0))}</td><td>{_e(pct(c.pct_before_fd))}</td>'
            f'<td>{_e(sh(c.after, 0))}</td><td>{_e(pct(c.pct_after_fd))}</td>'
            f'<td class="{cls(c.pct_after_fd - c.pct_before_fd)}">{_e(pp(c.pct_after_fd - c.pct_before_fd, 3))}</td></tr>'
            for c in res.classes)
        rows += (f'<tr class="total"><td>Total</td><td>{_e(sh(res.totals["before_fd"], 0))}</td><td>100.00%</td>'
                 f'<td>{_e(sh(res.totals["after_fd"], 0))}</td><td>100.00%</td><td></td></tr>'
                 f'<tr class="inv"><td>of which {_e(r.inputs.investor)}</td><td>&ndash;</td><td>&ndash;</td>'
                 f'<td>{_e(sh(iv.after_fd, 0))}</td><td>{_e(pct(iv.pct_after_fd))}</td>'
                 f'<td class="pos">{_e(pp(iv.delta_fd, 3))}</td></tr>')
        parts.append(f"""<div class="card plain"><h2>Ownership by class &middot; fully diluted</h2><div class="table-wrap"><table>
<tr><th>Class</th><th>Before shares</th><th>Before</th><th>After shares</th><th>After</th><th>Change</th></tr>{rows}</table></div>
<p class="muted" style="margin:12px 0 0">Post-money {_e(usd0(v['post_money']))} = pre-money {_e(usd0(v['pre_money']))} + proceeds
{_e(usd0(v['proceeds']))}. Implied at the share price: {_e(usd0(v['implied_post_basic']))} on outstanding shares,
{_e(usd0(v['implied_post_fd']))} fully diluted.</p></div>""")
    issues = "".join(
        f'<li><span class="pill {_e(i.severity)}">{_e(i.severity)}</span><div class="t">{_e(i.title)}</div>'
        f'<div class="d">{_e(i.arithmetic or i.detail[:320])}</div><div class="s">Source: {_e("; ".join(i.refs[:4]))}</div></li>'
        for i in r.top_issues)
    parts.append(f'<div class="card plain"><h2>Top data issues</h2><ul class="issues">{issues or "<li>No material data issues found.</li>"}</ul></div>')
    if r.ai is not None and not r.ai_error:
        parts.append(f"""<div class="card plain"><h2>Claude review</h2><p style="color:var(--ink-300);font-size:14px;line-height:1.6;margin:0">
{_e(r.ai.summary)}</p><p class="muted" style="margin:10px 0 0">{len(r.ai.findings)} verified finding(s) added to the workbook &middot;
{len(r.ai.discarded)} discarded (evidence not found in the sources) &middot; {len(r.ai.image_figures)} figure(s) read from slide images
&middot; {_e(r.ai.served_by or r.ai.model)}</p></div>""")
    elif r.ai_error:
        parts.append(f'<div class="card plain"><h2>Claude review</h2><p class="muted" style="margin:0">{_e(r.ai_error)}</p></div>')
    parts.append(f"""<div class="card plain"><form method="post" action="/jobs/{job_id}/rerun" enctype="multipart/form-data" data-xhr>
<details class="more"{" open" if not calc else ""} style="margin-top:0"><summary>Run again with different inputs</summary>
<div style="padding:0 16px 16px">{form_fields(params, ai_available, ai_default, open_advanced=not calc)}{_submit("Run again")}</div></details>
</form></div>""")
    return page(f"{r.company} {r.round_label}", "\n".join(parts), wide=True, script="window.MAX_UPLOAD_MB=0;" + FORM_JS)
