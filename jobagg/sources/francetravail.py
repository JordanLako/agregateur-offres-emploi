"""France Travail (ex-Pôle emploi).

Deux modes :
* **API officielle « Offres d'emploi v2 »** si FRANCE_TRAVAIL_CLIENT_ID / FRANCE_TRAVAIL_CLIENT_SECRET
  sont définis (inscription gratuite sur https://francetravail.io). Recommandé : fiable et rapide.
* **Repli HTML** sur candidat.francetravail.fr sinon.
"""

from __future__ import annotations

import os
import re
import time
from typing import Iterator, Optional

from bs4 import BeautifulSoup

from ..geo import commune
from ..models import JobOffer, SearchQuery
from ..utils import clean, parse_date
from .base import Source, SourceUnavailable

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
API_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SITE = "https://candidat.francetravail.fr"
HTML_SEARCH = SITE + "/offres/recherche"

# Codes « typeContrat » France Travail (le stage n'est pas un type de contrat côté FT)
API_CONTRACTS = {"cdi": "CDI", "cdd": "CDD", "interim": "MIS", "freelance": "LIB"}


def api_params(q: SearchQuery, start: int, size: int, place: Optional[dict]) -> dict:
    p: dict = {"motsCles": q.keywords, "range": f"{start}-{start + size - 1}", "sort": 1}
    if place:
        p["commune"] = place["code"]
        p["distance"] = q.radius_km
    elif re.fullmatch(r"\d{2,3}|2[AB]", q.location.strip(), re.I):
        p["departement"] = q.location.strip().upper()
    ct = sorted({API_CONTRACTS[c] for c in q.contracts if c in API_CONTRACTS})
    if ct:
        p["typeContrat"] = ",".join(ct)
    if "alternance" in q.contracts:
        p["natureContrat"] = "E2,FS"  # apprentissage, contrat de professionnalisation
    if q.max_age_days:
        p["publieeDepuis"] = min((d for d in (1, 3, 7, 14, 31) if d >= q.max_age_days), default=31)
    return p


def parse_api(data: dict) -> list[JobOffer]:
    out = []
    for o in data.get("resultats", []):
        sal = (o.get("salaire") or {}).get("libelle", "")
        url = f"{SITE}/offres/recherche/detail/{o['id']}"
        out.append(JobOffer(
            source="francetravail",
            source_id=o["id"],
            title=clean(o.get("intitule")),
            company=clean((o.get("entreprise") or {}).get("nom")),
            location=clean((o.get("lieuTravail") or {}).get("libelle")),
            url=url,
            contract=clean(o.get("typeContratLibelle") or o.get("typeContrat")),
            salary=clean(sal),
            description=clean(o.get("description")),
            published_at=parse_date(o.get("dateCreation")),
        ))
    return out


def parse_html(html: str) -> list[JobOffer]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for li in soup.select("li.result"):
        job_id = li.get("data-id-offre")
        a = li.select_one("a[href*='/detail/']")
        if not job_id and a:
            m = re.search(r"/detail/([A-Z0-9]+)", a["href"])
            job_id = m.group(1) if m else None
        if not job_id:
            continue
        t = li.select_one(".media-heading-title") or li.select_one("h2")
        sub = clean(li.select_one("p.subtext").get_text(" ")) if li.select_one("p.subtext") else ""
        company, _, location = sub.partition(" - ")
        if not location:
            company, location = "", company
        contract = li.select_one("p.contrat")
        desc = li.select_one("p.description")
        date = li.select_one("p.date")
        out.append(JobOffer(
            source="francetravail",
            source_id=job_id,
            title=clean(t.get_text(" ")) if t else "",
            company=clean(company),
            location=clean(location),
            url=f"{SITE}/offres/recherche/detail/{job_id}",
            contract=clean(contract.get_text(" ")) if contract else "",
            description=clean(desc.get_text(" ")) if desc else "",
            published_at=parse_date(clean(date.get_text(" "))) if date else None,
        ))
    return out


class FranceTravailSource(Source):
    name = "francetravail"
    label = "France Travail"
    delay = 0.4  # API : 3 appels/s max

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
        self.client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
        self._token: Optional[str] = None
        self._token_exp = 0.0

    @property
    def use_api(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        r = self.session.post(
            TOKEN_URL,
            params={"realm": "/partenaire"},
            data={"grant_type": "client_credentials", "client_id": self.client_id,
                  "client_secret": self.client_secret, "scope": "api_offresdemploiv2 o2dsoffre"},
            timeout=20,
        )
        if r.status_code >= 400:
            raise SourceUnavailable(f"France Travail : authentification refusée (HTTP {r.status_code})")
        tok = r.json()
        self._token = tok["access_token"]
        self._token_exp = time.time() + int(tok.get("expires_in", 1499))
        return self._token

    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        if self.use_api:
            yield from self._iter_api(q)
        else:
            yield from self._iter_html(q)

    def _iter_api(self, q: SearchQuery) -> Iterator[JobOffer]:
        place = commune(q.location, self.session) if q.location else None
        size = min(150, max(q.limit, 20))
        start = 0
        while start < 3000:  # plafond de l'API
            headers = {"Authorization": f"Bearer {self._get_token()}", "Accept": "application/json"}
            r = self.get(API_URL, params=api_params(q, start, size, place), headers=headers)
            if r.status_code == 204:
                return
            offers = parse_api(r.json())
            if not offers:
                return
            yield from offers
            if r.status_code != 206:  # 206 = contenu partiel, d'autres pages existent
                return
            start += size

    def _iter_html(self, q: SearchQuery) -> Iterator[JobOffer]:
        # Le site attend un code de lieu ; à défaut on ajoute la ville aux mots-clés.
        kw = f"{q.keywords} {q.location}".strip()
        params: dict = {"motsCles": kw, "offresPartenaires": "true", "tri": 1}
        ct = [API_CONTRACTS[c] for c in q.contracts if c in API_CONTRACTS]
        if ct:
            params["typeContrat"] = ",".join(sorted(set(ct)))
        if q.max_age_days:
            params["dureeCreation"] = min((d for d in (1, 3, 7, 14, 31) if d >= q.max_age_days), default=31)
        seen: set[str] = set()
        for page in range(0, 10):
            params["range"] = f"{page * 20}-{page * 20 + 19}"
            r = self.get(HTML_SEARCH, params=params)
            offers = [o for o in parse_html(r.text) if o.source_id not in seen]
            if not offers:
                return
            seen.update(o.source_id for o in offers)
            yield from offers
