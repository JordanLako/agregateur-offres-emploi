"""Modèles de données communs à toutes les sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


# Types de contrat normalisés acceptés en filtre.
CONTRACTS = ("cdi", "cdd", "stage", "alternance", "interim", "freelance")


@dataclass
class SearchQuery:
    """Critères de recherche, identiques pour toutes les plateformes."""

    keywords: str
    location: str = ""
    radius_km: int = 30
    contracts: list[str] = field(default_factory=list)  # sous-ensemble de CONTRACTS
    remote: bool = False
    max_age_days: Optional[int] = None  # 1, 7, 30… ; None = pas de limite
    limit: int = 50  # nombre max d'offres *par source*


@dataclass
class JobOffer:
    """Offre d'emploi normalisée."""

    source: str
    source_id: str
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    contract: str = ""
    salary: str = ""
    remote: str = ""
    description: str = ""
    published_at: Optional[datetime] = None
    also_on: list[str] = field(default_factory=list)  # autres sources (doublons fusionnés)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat() if self.published_at else None
        return d
