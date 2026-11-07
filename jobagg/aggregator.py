"""Interroge toutes les sources en parallèle, filtre, dédoublonne et trie."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from .models import JobOffer, SearchQuery
from .sources import SOURCES, Source, SourceUnavailable
from .utils import normalize, now

log = logging.getLogger("jobagg")

# Mots qui identifient chaque type de contrat dans les libellés des différentes plateformes.
CONTRACT_WORDS = {
    "cdi": ("cdi", "permanent", "indetermine"),
    "cdd": ("cdd", "temporaire", "determinee", "fixed term"),
    "stage": ("stage", "internship", "intern"),
    "alternance": ("alternance", "apprenti", "professionnalisation"),
    "interim": ("interim", "temporaire", "mission"),
    "freelance": ("freelance", "independant", "liberal", "indep"),
}


@dataclass
class SourceReport:
    source: str
    label: str
    count: int = 0
    error: Optional[str] = None
    seconds: float = 0.0


@dataclass
class SearchResult:
    query: SearchQuery
    offers: list[JobOffer] = field(default_factory=list)
    reports: list[SourceReport] = field(default_factory=list)
    duplicates_merged: int = 0


def matches_contract(offer: JobOffer, contracts: Iterable[str]) -> bool:
    contracts = list(contracts)
    if not contracts or not offer.contract:
        return True  # contrat inconnu : on garde l'offre
    text = normalize(offer.contract)
    return any(w in text for c in contracts for w in CONTRACT_WORDS.get(c, (c,)))


def is_recent(offer: JobOffer, max_age_days: Optional[int], ref: Optional[datetime] = None) -> bool:
    if not max_age_days or offer.published_at is None:
        return True
    ref = ref or now()
    pub = offer.published_at if offer.published_at.tzinfo else offer.published_at.replace(tzinfo=timezone.utc)
    return ref - pub <= timedelta(days=max_age_days, hours=12)


def dedup_key(o: JobOffer) -> str:
    company = normalize(o.company)
    for suffix in (" sas", " sa", " sarl", " group", " groupe", " france"):
        if company.endswith(suffix):
            company = company[: -len(suffix)]
    return f"{normalize(o.title)}|{company}"


def deduplicate(offers: list[JobOffer]) -> tuple[list[JobOffer], int]:
    """Fusionne les offres identiques (même intitulé + même entreprise) publiées sur plusieurs sites.

    L'offre conservée est la plus complète ; les autres sources sont listées dans ``also_on``.
    """
    groups: dict[str, list[JobOffer]] = {}
    for o in offers:
        if not o.company:  # sans entreprise, impossible de dédoublonner sûrement
            groups[o.uid] = [o]
        else:
            groups.setdefault(dedup_key(o), []).append(o)
    merged = []
    for group in groups.values():
        best = max(group, key=lambda o: sum(bool(v) for v in (o.description, o.salary, o.contract,
                                                                o.location, o.published_at)))
        others = [o for o in group if o is not best]
        best.also_on = sorted({o.source for o in others if o.source != best.source} | set(best.also_on))
        if not best.salary:
            best.salary = next((o.salary for o in others if o.salary), "")
        dates = [o.published_at for o in group if o.published_at]
        if dates:
            best.published_at = max(dates)
        merged.append(best)
    return merged, len(offers) - len(merged)


def sort_offers(offers: list[JobOffer]) -> list[JobOffer]:
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(offers, key=lambda o: o.published_at or epoch, reverse=True)


def search(
    q: SearchQuery,
    sources: Optional[Iterable[str]] = None,
    dedup: bool = True,
    on_progress: Optional[Callable[[SourceReport], None]] = None,
    source_factory: Callable[[str], Source] = lambda n: SOURCES[n](),
) -> SearchResult:
    import time

    names = list(sources) if sources else list(SOURCES)
    result = SearchResult(query=q)
    all_offers: list[JobOffer] = []

    def run(name: str) -> tuple[SourceReport, list[JobOffer]]:
        src = source_factory(name)
        rep = SourceReport(source=name, label=src.label)
        t0 = time.monotonic()
        offers: list[JobOffer] = []
        try:
            offers = src.search(q)
        except SourceUnavailable as e:
            rep.error = str(e)
        except Exception as e:  # une source en panne ne doit pas bloquer les autres
            log.debug("Erreur %s", name, exc_info=True)
            rep.error = f"{type(e).__name__}: {e}"
        rep.seconds = time.monotonic() - t0
        rep.count = len(offers)
        return rep, offers

    with ThreadPoolExecutor(max_workers=len(names) or 1) as pool:
        futures = [pool.submit(run, n) for n in names]
        for fut in as_completed(futures):
            rep, offers = fut.result()
            result.reports.append(rep)
            all_offers.extend(offers)
            if on_progress:
                on_progress(rep)

    order = {n: i for i, n in enumerate(names)}
    result.reports.sort(key=lambda r: order[r.source])

    filtered = [o for o in all_offers if matches_contract(o, q.contracts) and is_recent(o, q.max_age_days)]
    if dedup:
        filtered, result.duplicates_merged = deduplicate(filtered)
    result.offers = sort_offers(filtered)
    return result
