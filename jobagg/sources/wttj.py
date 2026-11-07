"""Welcome to the Jungle : index Algolia public utilisé par le site."""

from __future__ import annotations

import os
from typing import Iterator, Optional

from ..geo import geocode
from ..models import JobOffer, SearchQuery
from ..utils import clean, parse_date
from .base import Source

# Identifiants « search-only » publics, embarqués dans le front-end du site.
# Surchargeables par variables d'environnement s'ils changent.
APP_ID = os.getenv("WTTJ_ALGOLIA_APP_ID", "CSEKHVMS53")
API_KEY = os.getenv("WTTJ_ALGOLIA_API_KEY", "4bd8f6215d0cc52b26430765769e65a0")
INDEX = os.getenv("WTTJ_ALGOLIA_INDEX", "wttj_jobs_production_fr")

CONTRACT_MAP = {"cdi": "full_time", "cdd": "temporary", "interim": "temporary", "stage": "internship",
                "alternance": "apprenticeship", "freelance": "freelance"}
CONTRACT_LABELS = {"full_time": "CDI", "temporary": "CDD / Temporaire", "internship": "Stage",
                   "apprenticeship": "Alternance", "freelance": "Freelance", "part_time": "Temps partiel",
                   "vie": "VIE", "fixed_term": "CDD", "other": "Autre"}
REMOTE_LABELS = {"fulltime": "Télétravail total", "partial": "Télétravail partiel",
                 "punctual": "Télétravail ponctuel", "no": "Sur site"}


def build_body(q: SearchQuery, page: int, coords: Optional[tuple[float, float]]) -> dict:
    filters = []
    ct = sorted({CONTRACT_MAP[c] for c in q.contracts if c in CONTRACT_MAP})
    if ct:
        filters.append("(" + " OR ".join(f"contract_type:{c}" for c in ct) + ")")
    if q.remote:
        filters.append("(remote:fulltime OR remote:partial)")
    body = {"query": q.keywords, "hitsPerPage": 30, "page": page}
    if filters:
        body["filters"] = " AND ".join(filters)
    if coords:
        body["aroundLatLng"] = f"{coords[0]},{coords[1]}"
        body["aroundRadius"] = q.radius_km * 1000
    elif q.location:
        body["query"] = f"{q.keywords} {q.location}"
    return body


def parse_hits(data: dict) -> list[JobOffer]:
    out = []
    for h in data.get("hits", []):
        org = h.get("organization") or {}
        offices = h.get("offices") or []
        loc = ""
        if offices:
            o = offices[0]
            loc = ", ".join(x for x in (o.get("city"), o.get("country")) if x)
        smin, smax = h.get("salary_minimum") or h.get("salary_yearly_minimum"), h.get("salary_maximum")
        salary = ""
        if smin or smax:
            cur = h.get("salary_currency") or "EUR"
            period = {"yearly": "/an", "monthly": "/mois", "daily": "/jour"}.get(h.get("salary_period") or "", "")
            salary = " – ".join(f"{int(v):,}".replace(",", " ") for v in (smin, smax) if v) + f" {cur}{period}"
        org_slug, slug = org.get("slug", ""), h.get("slug", "")
        out.append(JobOffer(
            source="wttj",
            source_id=str(h.get("reference") or h.get("objectID")),
            title=clean(h.get("name")),
            company=clean(org.get("name")),
            location=loc,
            url=f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}" if slug else "",
            contract=CONTRACT_LABELS.get(h.get("contract_type") or "", h.get("contract_type") or ""),
            salary=salary,
            remote=REMOTE_LABELS.get(h.get("remote") or "", ""),
            description=clean(h.get("summary")),
            published_at=parse_date(h.get("published_at")),
        ))
    return out


class WelcomeToTheJungleSource(Source):
    name = "wttj"
    label = "Welcome to the Jungle"
    delay = 0.5

    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        url = f"https://{APP_ID.lower()}-dsn.algolia.net/1/indexes/{INDEX}/query"
        headers = {
            "X-Algolia-Application-Id": APP_ID,
            "X-Algolia-API-Key": API_KEY,
            "Referer": "https://www.welcometothejungle.com/",
            "Origin": "https://www.welcometothejungle.com",
            "Content-Type": "application/json",
        }
        coords = geocode(q.location, self.session) if q.location else None
        page = 0
        while True:
            r = self.post(url, json=build_body(q, page, coords), headers=headers)
            data = r.json()
            hits = parse_hits(data)
            if not hits:
                return
            yield from hits
            page += 1
            if page >= data.get("nbPages", 0):
                return
