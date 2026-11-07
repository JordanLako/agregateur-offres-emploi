"""Classe de base des connecteurs."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterator, Optional

import requests

from ..http import Throttle, make_session
from ..models import JobOffer, SearchQuery

log = logging.getLogger("jobagg")


class SourceUnavailable(Exception):
    """La source ne peut pas être interrogée (clé API manquante, blocage…)."""


class Source(ABC):
    #: identifiant court utilisé en ligne de commande
    name: str = ""
    #: nom affiché
    label: str = ""
    #: délai minimal entre deux requêtes (secondes)
    delay: float = 1.5
    #: nécessite une configuration (clé API) ?
    requires_config: bool = False

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or make_session()
        self.throttle = Throttle(self.delay)

    def is_configured(self) -> bool:
        return True

    # --- HTTP -------------------------------------------------------------
    def get(self, url: str, **kw) -> requests.Response:
        self.throttle.wait()
        kw.setdefault("timeout", 20)
        r = self.session.get(url, **kw)
        self._check(r)
        return r

    def post(self, url: str, **kw) -> requests.Response:
        self.throttle.wait()
        kw.setdefault("timeout", 20)
        r = self.session.post(url, **kw)
        self._check(r)
        return r

    def _check(self, r: requests.Response) -> None:
        if r.status_code in (401, 403, 999):
            raise SourceUnavailable(f"{self.label} a refusé la requête (HTTP {r.status_code})")
        r.raise_for_status()

    # --- recherche --------------------------------------------------------
    @abstractmethod
    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        """Génère les offres page par page (la limite est appliquée par search())."""

    def search(self, q: SearchQuery) -> list[JobOffer]:
        if not self.is_configured():
            raise SourceUnavailable(f"{self.label} n'est pas configuré (voir README)")
        out: list[JobOffer] = []
        seen: set[str] = set()
        for offer in self.iter_offers(q):
            if offer.source_id in seen:
                continue
            seen.add(offer.source_id)
            out.append(offer)
            if len(out) >= q.limit:
                break
        return out
