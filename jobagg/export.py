"""Exports : tableau terminal, JSON, CSV, page HTML autonome."""

from __future__ import annotations

import csv
import html
import io
import json
import shutil
from datetime import datetime

from .aggregator import SearchResult
from .models import JobOffer
from .sources import SOURCES
from .utils import now, truncate

FIELDS = ["source", "also_on", "title", "company", "location", "contract", "salary", "remote",
          "published_at", "url", "description"]


def _label(name: str) -> str:
    cls = SOURCES.get(name)
    return cls.label if cls else name


def _age(dt: datetime | None) -> str:
    if not dt:
        return ""
    days = (now() - dt).days
    if days <= 0:
        return "aujourd'hui"
    if days == 1:
        return "hier"
    return f"{days} j"


def to_json(result: SearchResult) -> str:
    return json.dumps(
        {
            "query": result.query.__dict__,
            "generated_at": now().isoformat(),
            "sources": [r.__dict__ for r in result.reports],
            "count": len(result.offers),
            "offers": [o.to_dict() for o in result.offers],
        },
        ensure_ascii=False,
        indent=2,
    )


def to_csv(result: SearchResult) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore", delimiter=";")
    w.writeheader()
    for o in result.offers:
        d = o.to_dict()
        d["also_on"] = ",".join(o.also_on)
        w.writerow(d)
    # BOM pour qu'Excel détecte l'UTF-8
    return "﻿" + buf.getvalue()


def to_table(result: SearchResult, color: bool = True) -> str:
    width = shutil.get_terminal_size((140, 40)).columns
    cols = [("Source", 13), ("Publiée", 11), ("Intitulé", 0), ("Entreprise", 22), ("Lieu", 20), ("Contrat", 10)]
    fixed = sum(w for _, w in cols if w) + 3 * (len(cols) - 1)
    title_w = max(20, width - fixed)
    cols = [(n, w or title_w) for n, w in cols]

    bold = "\033[1m" if color else ""
    dim = "\033[2m" if color else ""
    reset = "\033[0m" if color else ""

    lines = [bold + " │ ".join(n.ljust(w) for n, w in cols) + reset,
             "─┼─".join("─" * w for _, w in cols)]
    for o in result.offers:
        src = _label(o.source) + (f" +{len(o.also_on)}" if o.also_on else "")
        vals = [src, _age(o.published_at), o.title, o.company, o.location, o.contract]
        lines.append(" │ ".join(truncate(v, w).ljust(w) for v, (_, w) in zip(vals, cols)))
        if o.url:
            lines.append(dim + " " * (cols[0][1] + cols[1][1] + 6) + o.url + reset)
    return "\n".join(lines)


def to_html(result: SearchResult) -> str:
    q = result.query
    rows = []
    for o in result.offers:
        sources = " ".join(f'<span class="tag s-{html.escape(s)}">{html.escape(_label(s))}</span>'
                           for s in [o.source, *o.also_on])
        rows.append(
            "<tr data-source=\"{src}\">"
            "<td>{sources}</td><td data-sort=\"{ts}\">{age}</td>"
            "<td><a href=\"{url}\" target=\"_blank\" rel=\"noopener\">{title}</a>"
            "<div class=\"desc\">{desc}</div></td>"
            "<td>{company}</td><td>{loc}</td><td>{contract}</td><td>{salary}</td></tr>".format(
                src=html.escape(" ".join([o.source, *o.also_on])),
                sources=sources,
                ts=o.published_at.timestamp() if o.published_at else 0,
                age=html.escape(o.published_at.strftime("%d/%m/%Y") if o.published_at else ""),
                url=html.escape(o.url),
                title=html.escape(o.title),
                desc=html.escape(truncate(o.description, 220)),
                company=html.escape(o.company),
                loc=html.escape(o.location),
                contract=html.escape(" ".join(x for x in (o.contract, o.remote) if x)),
                salary=html.escape(o.salary),
            )
        )
    reports = "".join(
        f'<li class="{"err" if r.error else "ok"}"><b>{html.escape(r.label)}</b> : '
        + (html.escape(r.error) if r.error else f"{r.count} offre(s)") + "</li>"
        for r in result.reports
    )
    checkboxes = "".join(
        f'<label><input type="checkbox" value="{html.escape(r.source)}" checked> {html.escape(r.label)}</label>'
        for r in result.reports if r.count
    )
    title = f"Offres « {q.keywords} »" + (f" – {q.location}" if q.location else "")
    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        generated=now().astimezone().strftime("%d/%m/%Y %H:%M"),
        count=len(result.offers),
        dups=result.duplicates_merged,
        reports=reports,
        checkboxes=checkboxes,
        rows="\n".join(rows),
    )


_HTML_TEMPLATE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#fff; --fg:#1b1b1f; --muted:#666; --line:#e5e5ea; --accent:#2f5bea; --head:#f6f6f8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16171a; --fg:#ececf0; --muted:#9a9aa3;
  --line:#2c2d33; --accent:#7c9cff; --head:#1f2024; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,sans-serif; margin:0 auto;
  padding:16px; max-width:1400px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .meta {{ color:var(--muted); margin-bottom:12px; }}
ul.rep {{ list-style:none; padding:0; display:flex; flex-wrap:wrap; gap:6px 16px; margin:0 0 12px; }}
ul.rep .err {{ color:#c0392b; }}
.bar {{ display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; margin-bottom:12px; }}
.bar input[type=search] {{ flex:1 1 260px; padding:8px 10px; border:1px solid var(--line); border-radius:6px;
  background:var(--bg); color:var(--fg); }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; }}
th,td {{ text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ background:var(--head); cursor:pointer; position:sticky; top:0; user-select:none; }}
a {{ color:var(--accent); text-decoration:none; font-weight:600; }} a:hover {{ text-decoration:underline; }}
.desc {{ color:var(--muted); font-size:12px; margin-top:2px; }}
.tag {{ display:inline-block; font-size:11px; padding:1px 6px; border-radius:10px; margin:0 3px 3px 0;
  background:var(--head); border:1px solid var(--line); white-space:nowrap; }}
.s-linkedin {{ border-color:#0a66c2; }} .s-hellowork {{ border-color:#ff6a00; }} .s-wttj {{ border-color:#ffcd00; }}
.s-francetravail {{ border-color:#1e3d8f; }} .s-apec {{ border-color:#7b1fa2; }} .s-adzuna {{ border-color:#2e7d32; }}
</style></head><body>
<h1>{title}</h1>
<div class="meta">{count} offres · {dups} doublon(s) fusionné(s) · généré le {generated}</div>
<ul class="rep">{reports}</ul>
<div class="bar"><input type="search" id="q" placeholder="Filtrer (intitulé, entreprise, lieu…)">{checkboxes}</div>
<div class="wrap"><table id="t"><thead><tr>
<th>Source</th><th data-num>Publiée</th><th>Intitulé</th><th>Entreprise</th><th>Lieu</th><th>Contrat</th><th>Salaire</th>
</tr></thead><tbody>
{rows}
</tbody></table></div>
<script>
const q = document.getElementById('q'), boxes = [...document.querySelectorAll('.bar input[type=checkbox]')];
const rows = [...document.querySelectorAll('#t tbody tr')];
function apply() {{
  const s = q.value.toLowerCase(), on = new Set(boxes.filter(b => b.checked).map(b => b.value));
  rows.forEach(r => {{
    const okSrc = r.dataset.source.split(' ').some(x => on.has(x));
    r.style.display = okSrc && r.textContent.toLowerCase().includes(s) ? '' : 'none';
  }});
}}
q.addEventListener('input', apply); boxes.forEach(b => b.addEventListener('change', apply));
document.querySelectorAll('#t th').forEach((th, i) => th.addEventListener('click', () => {{
  const tb = th.closest('table').tBodies[0], asc = th.dataset.dir !== 'asc';
  th.dataset.dir = asc ? 'asc' : 'desc';
  const val = r => th.hasAttribute('data-num') ? +r.cells[i].dataset.sort : r.cells[i].textContent.trim().toLowerCase();
  [...tb.rows].sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * (asc ? 1 : -1))
    .forEach(r => tb.appendChild(r));
}}));
</script></body></html>
"""
