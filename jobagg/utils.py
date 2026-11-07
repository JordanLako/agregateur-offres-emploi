"""Fonctions utilitaires : dates relatives, normalisation de texte."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

_UNITS = {
    "minute": "minutes", "min": "minutes", "heure": "hours", "hour": "hours", "h": "hours",
    "jour": "days", "day": "days", "j": "days",
    "semaine": "weeks", "week": "weeks", "sem": "weeks",
    "mois": "months", "month": "months",
    "an": "years", "année": "years", "annee": "years", "year": "years",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(value: Optional[str], ref: Optional[datetime] = None) -> Optional[datetime]:
    """Parse une date ISO ou un texte relatif (« il y a 3 jours », « hier », « 2 weeks ago »)."""
    if not value:
        return None
    value = value.strip()
    ref = ref or now()

    # ISO 8601 / AAAA-MM-JJ
    iso = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # JJ/MM/AAAA
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            return None

    low = strip_accents(value.lower())
    if any(w in low for w in ("aujourd", "today", "a l'instant", "just now", "instant")):
        return ref
    if "avant-hier" in low:
        return ref - timedelta(days=2)
    if "hier" in low or "yesterday" in low:
        return ref - timedelta(days=1)

    m = re.search(r"(\d+)\s*\+?\s*([a-z]+)", low)
    if m:
        n = int(m.group(1))
        word = m.group(2).rstrip("s") or m.group(2)
        unit = _UNITS.get(word) or _UNITS.get(m.group(2))
        if unit is None:
            for k, u in _UNITS.items():
                if len(k) > 1 and word.startswith(k):
                    unit = u
                    break
        if unit == "months":
            return ref - timedelta(days=30 * n)
        if unit == "years":
            return ref - timedelta(days=365 * n)
        if unit:
            return ref - timedelta(**{unit: n})
    return None


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    """Normalise un texte pour la détection de doublons."""
    s = strip_accents((s or "").lower())
    s = re.sub(r"\(.*?\)", " ", s)  # « (H/F) », « (F/H) »…
    s = re.sub(r"\b(h\s*/\s*f|f\s*/\s*h|m\s*/\s*f|f\s*/\s*m|hf|fh)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def clean(s: Optional[str]) -> str:
    return " ".join((s or "").split())


def truncate(s: str, n: int) -> str:
    s = clean(s)
    return s if len(s) <= n else s[: n - 1] + "…"
