"""APEC (offres cadres) : web service JSON utilisé par apec.fr."""

from __future__ import annotations

from typing import Iterator

from ..models import JobOffer, SearchQuery
from ..utils import clean, normalize, parse_date
from .base import Source

API_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"
DETAIL_URL = "https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{}"

# Codes de type de contrat APEC (seuls les codes connus sont envoyés ; le reste est filtré ensuite)
CONTRACT_CODES = {"cdi": "101888", "cdd": "101887", "interim": "101889"}
CONTRACT_LABELS = {"101888": "CDI", "101887": "CDD", "101889": "Intérim"}
PAGE = 20


def build_body(q: SearchQuery, start: int) -> dict:
    body = {
        "motsCles": q.keywords,
        "lieux": [],
        "fonctions": [], "statutPoste": [], "typesConvention": [], "niveauxExperience": [],
        "secteursActivite": [],
        "typesContrat": [CONTRACT_CODES[c] for c in q.contracts if c in CONTRACT_CODES],
        "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
        "pagination": {"range": PAGE, "startIndex": start},
        "activeFiltre": True,
        "pointGeolocDeReference": {"distance": 0},
    }
    return body


def parse_results(data: dict) -> list[JobOffer]:
    out = []
    for r in data.get("resultats", []):
        num = str(r.get("numeroOffre") or r.get("id"))
        out.append(JobOffer(
            source="apec",
            source_id=num,
            title=clean(r.get("intitule")),
            company=clean(r.get("nomCommercial")),
            location=clean(r.get("lieuTexte")),
            url=DETAIL_URL.format(num),
            contract=CONTRACT_LABELS.get(str(r.get("typeContrat")), ""),
            salary=clean(r.get("salaireTexte")),
            description=clean(r.get("texteOffre")),
            published_at=parse_date(r.get("datePublication")),
        ))
    return out


class ApecSource(Source):
    name = "apec"
    label = "APEC"

    def iter_offers(self, q: SearchQuery) -> Iterator[JobOffer]:
        # Le filtre géographique APEC exige des codes internes : on filtre sur le texte du lieu.
        loc = normalize(q.location) if q.location and q.location.lower() != "france" else ""
        start = 0
        while start < 2000:
            r = self.post(API_URL, json=build_body(q, start),
                          headers={"Content-Type": "application/json", "Referer": "https://www.apec.fr/"})
            data = r.json()
            offers = parse_results(data)
            if not offers:
                return
            for o in offers:
                if not loc or loc in normalize(o.location):
                    yield o
            start += PAGE
            if start >= data.get("totalCount", 0):
                return
