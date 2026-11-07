"""Adzuna : API officielle (clé gratuite sur https://developer.adzuna.com).

Agrège de nombreux job boards et sites carrière français (dont des offres Indeed, Monster…).
"""

from __future__ import annotations

import os
from typing import Iterator

from ..models import JobOffer, SearchQuery
from ..utils import clean, parse_date
from .base import Source

API_URL = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"
PAGE = 50


def build_params(q: SearchQuery, app_id: str, app_key: str) -> dict:
    p = {"app_id": app_id, "app_key": app_key, "results_per_page": PAGE, "what": q.keywords,
         "sort_by": "date", "content-type": "application/json"}
    if q.location and q.location.lower() != "france":
        p["where"] = q.location
        p["distance"] = q.radius_km
    if "cdi" in q.contracts:
        p["permanent"] = 1
    elif q.contracts and set(q.contracts) <= {"cdd", "interim", "freelance"}:
        p["contract"] = 1
    if q.max_age_days:
        p["max_days_old"] = q.max_age_days
    return p


def parse_results(data: dict) -> list[JobOffer]:
    out = []
    for r in data.get("results", []):
        smin, smax = r.get("salary_min"), r.get("salary_max")
        salary = ""
        if smin or smax:
            salary = " – ".join(f"{int(v):,}".replace(",", " ") for v in (smin, smax) if v) + " €/an"
            if r.get("salary_is_predicted") in ("1", 1):
                salary += " (estimé)"
        out.append(JobOffer(
            source="adzuna",
            source_id=str(r.get("id")),
            title=clean(r.get("title")),
            company=clean((r.get("company") or {}).get("display_name")),
            location=clean((r.get("location") or {}).get("display_name")),
            url=r.get("redirect_url", ""),
            contract={"permanent": "CDI", "contract": "CDD"}.get(r.get("contract_type") or "", ""),
            salary=salary,
            description=clean(r.get("description")),
            published_at=parse_date(r.get("created")),
        ))
    return out


class AdzunaSource(Source):
    name = "adzuna"
    label = "Adzuna"
    delay = 1.0
    requires_config = True

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.app_id = os.getenv("ADZUNA_APP_ID", "")
        self.app_key = os.getenv("ADZUNA_APP_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        params = build_params(q, self.app_id, self.app_key)
        for page in range(1, 21):
            r = self.get(API_URL.format(page=page), params=params)
            data = r.json()
            offers = parse_results(data)
            if not offers:
                return
            yield from offers
            if page * PAGE >= data.get("count", 0):
                return
