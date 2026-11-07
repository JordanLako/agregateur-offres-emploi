"""HelloWork : scraping de la page de résultats."""

from __future__ import annotations

import json
import re
from typing import Iterator

from bs4 import BeautifulSoup

from ..models import JobOffer, SearchQuery
from ..utils import clean, parse_date
from .base import Source

BASE = "https://www.hellowork.com"
SEARCH_URL = BASE + "/fr-fr/emploi/recherche.html"

CONTRACT_MAP = {"cdi": "CDI", "cdd": "CDD", "interim": "Travail_temp", "stage": "Stage",
                "alternance": "Alternance", "freelance": "Independant"}


def build_params(q: SearchQuery, page: int) -> list[tuple[str, str]]:
    p: list[tuple[str, str]] = [("k", q.keywords)]
    if q.location:
        p += [("l", q.location), ("ray", str(q.radius_km))]
    for c in q.contracts:
        if c in CONTRACT_MAP:
            p.append(("c", CONTRACT_MAP[c]))
    if q.remote:
        p.append(("t", "Complet"))  # télétravail complet
    if q.max_age_days:
        p.append(("d", "j" if q.max_age_days <= 1 else "s" if q.max_age_days <= 7 else "m"))
    if page > 1:
        p.append(("p", str(page)))
    return p


_POSTCODE = re.compile(r"\b\d{2,3}\b|\b\d{5}\b|- \d{2}\b")
_CONTRACTS = ("CDI", "CDD", "Intérim", "Interim", "Stage", "Alternance", "Freelance", "Indépendant")


def parse_results(html: str) -> list[JobOffer]:
    soup = BeautifulSoup(html, "lxml")
    offers: list[JobOffer] = []
    for li in soup.select("li[data-id-storage-item-id]"):
        job_id = li["data-id-storage-item-id"]
        title_in = li.select_one("input[name='title']")
        company_in = li.select_one("input[name='company']")
        title = clean(title_in.get("value")) if title_in else ""
        company = clean(company_in.get("value")) if company_in else ""
        link = li.select_one("a[href*='/emplois/']")
        if not title and link:
            h3 = link.select_one("h3 p, h3") or link
            title = clean(h3.get_text(" "))
        if not title:
            continue
        url = BASE + link["href"] if link and link["href"].startswith("/") else (
            link["href"] if link else f"{BASE}/fr-fr/emplois/{job_id}.html")

        location = contract = salary = ""
        for tag in li.select("div[class*='tw-tag'], [data-cy='localisationCard'], [data-cy='contractCard']"):
            t = clean(tag.get_text(" "))
            if not t:
                continue
            if "€" in t and not salary:
                salary = t
            elif any(t.startswith(c) for c in _CONTRACTS) and not contract:
                contract = t
            elif not location and (_POSTCODE.search(t) or tag.get("data-cy") == "localisationCard"):
                location = t
        date_el = li.select_one("div.tw-text-grey-500, [class*='tw-typo-s'][class*='grey']")
        published = parse_date(clean(date_el.get_text(" "))) if date_el else None
        offers.append(JobOffer("hellowork", job_id, title, company, location, url,
                               contract=contract, salary=salary, published_at=published))

    if not offers:
        offers = _parse_jsonld(soup)
    return offers


def _parse_jsonld(soup: BeautifulSoup) -> list[JobOffer]:
    """Repli : données structurées schema.org (JobPosting) si présentes."""
    offers = []
    for s in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(s.string or "")
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("itemListElement", [data])
        for it in items:
            it = it.get("item", it) if isinstance(it, dict) else {}
            if it.get("@type") != "JobPosting":
                continue
            url = it.get("url", "")
            m = re.search(r"/(\d+)\.html", url)
            loc = it.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            offers.append(JobOffer(
                "hellowork", m.group(1) if m else url, clean(it.get("title")),
                clean((it.get("hiringOrganization") or {}).get("name")),
                clean(addr.get("addressLocality")), url,
                contract=clean(str(it.get("employmentType", ""))),
                published_at=parse_date(it.get("datePosted")),
            ))
    return offers


class HelloWorkSource(Source):
    name = "hellowork"
    label = "HelloWork"

    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        seen: set[str] = set()
        for page in range(1, 20):
            r = self.get(SEARCH_URL, params=build_params(q, page))
            offers = [o for o in parse_results(r.text) if o.source_id not in seen]
            if not offers:  # page vide, ou le site renvoie la dernière page en boucle
                return
            seen.update(o.source_id for o in offers)
            yield from offers
