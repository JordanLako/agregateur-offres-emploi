"""Géocodage des villes françaises via l'API officielle geo.api.gouv.fr (gratuite, sans clé)."""

from __future__ import annotations

import functools
import logging
import re
from typing import Optional

import requests

log = logging.getLogger("jobagg")

GEO_URL = "https://geo.api.gouv.fr/communes"


@functools.lru_cache(maxsize=128)
def _lookup(name: str, session: requests.Session) -> Optional[dict]:
    params = {"fields": "code,nom,codeDepartement,centre,codesPostaux", "boost": "population", "limit": 1}
    if re.fullmatch(r"\d{5}", name):
        params["codePostal"] = name
    else:
        params["nom"] = name
    try:
        r = session.get(GEO_URL, params=params, timeout=10)
        r.raise_for_status()
        res = r.json()
        return res[0] if res else None
    except (requests.RequestException, ValueError) as e:
        log.debug("Géocodage impossible pour %r : %s", name, e)
        return None


def commune(name: str, session: Optional[requests.Session] = None) -> Optional[dict]:
    """Retourne {code (INSEE), nom, codeDepartement, centre:{coordinates:[lon,lat]}} ou None."""
    name = (name or "").strip()
    if not name or name.lower() == "france":
        return None
    session = session or requests.Session()
    return _lookup(name, session)


def geocode(name: str, session: Optional[requests.Session] = None) -> Optional[tuple[float, float]]:
    """(latitude, longitude) d'une commune, ou None."""
    c = commune(name, session)
    if c and c.get("centre"):
        lon, lat = c["centre"]["coordinates"]
        return lat, lon
    return None
