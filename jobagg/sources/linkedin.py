"""LinkedIn : API « guest » publique (fragments HTML), sans connexion."""

from __future__ import annotations

import re
from typing import Iterator

from bs4 import BeautifulSoup

from ..models import JobOffer, SearchQuery
from ..utils import clean, parse_date
from .base import Source

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PAGE_SIZE = 10  # l'API guest renvoie 10 cartes par appel

CONTRACT_MAP = {"cdi": "F", "cdd": "C", "interim": "T", "stage": "I", "alternance": "I", "freelance": "C"}


def build_params(q: SearchQuery, start: int) -> dict:
    p = {"keywords": q.keywords, "location": q.location or "France", "start": start}
    if q.location:
        p["distance"] = max(5, round(q.radius_km / 1.609))  # LinkedIn compte en miles
    jt = sorted({CONTRACT_MAP[c] for c in q.contracts if c in CONTRACT_MAP})
    if jt:
        p["f_JT"] = ",".join(jt)
    if q.remote:
        p["f_WT"] = "2"
    if q.max_age_days:
        p["f_TPR"] = f"r{q.max_age_days * 86400}"
    return p


def _text(el) -> str:
    return clean(el.get_text(" ")) if el else ""


def parse_cards(html: str) -> list[JobOffer]:
    soup = BeautifulSoup(html, "lxml")
    offers = []
    for card in soup.select("div.base-card, div.job-search-card"):
        urn = card.get("data-entity-urn", "")
        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        href = link.get("href", "") if link else ""
        m = re.search(r"jobPosting:(\d+)", urn) or re.search(r"-(\d+)(?:[/?]|$)", href.split("?")[0] + "?")
        if not m:
            continue
        job_id = m.group(1)
        title = _text(card.select_one("h3.base-search-card__title"))
        company = _text(card.select_one("h4.base-search-card__subtitle"))
        # Offres « masquées » (****) renvoyées aux visiteurs non connectés
        if not title or title.count("*") > len(title) * 0.3:
            continue
        time_el = card.select_one("time")
        published = None
        if time_el:
            published = parse_date(time_el.get("datetime")) or parse_date(_text(time_el))
        salary = _text(card.select_one("span.job-search-card__salary-info"))
        offers.append(JobOffer(
            source="linkedin",
            source_id=job_id,
            title=title,
            company=company,
            location=_text(card.select_one("span.job-search-card__location")),
            url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            salary=salary,
            published_at=published,
        ))
    return offers


class LinkedInSource(Source):
    name = "linkedin"
    label = "LinkedIn"
    delay = 2.5

    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        start = 0
        max_start = q.limit * 3  # garde-fou
        seen: set[str] = set()
        while start <= max_start:
            r = self.get(SEARCH_URL, params=build_params(q, start))
            cards = [c for c in parse_cards(r.text) if c.source_id not in seen]
            if not cards:
                return
            seen.update(c.source_id for c in cards)
            yield from cards
            start += PAGE_SIZE
