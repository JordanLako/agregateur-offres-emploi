"""Interface en ligne de commande : `jobagg "développeur python" -l Lyon`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .aggregator import SourceReport, search
from .export import to_csv, to_html, to_json, to_table
from .models import CONTRACTS, SearchQuery
from .sources import SOURCES

AGE_CHOICES = {"24h": 1, "3j": 3, "semaine": 7, "mois": 30}


def load_dotenv(path: Path = Path(".env")) -> None:
    """Charge un fichier .env minimal (CLE=valeur) sans dépendance externe."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jobagg",
        description="Recherche simultanée d'offres d'emploi sur LinkedIn, HelloWork, Welcome to the Jungle, "
                    "France Travail, APEC et Adzuna.",
        epilog='Exemple : jobagg "data analyst" -l Lyon -c cdi -c cdd --age semaine -o offres.html',
    )
    p.add_argument("keywords", nargs="?", help="mots-clés (ex. « développeur python »)")
    p.add_argument("-l", "--location", default="", help="ville, code postal ou département (ex. Lyon, 69003, 33)")
    p.add_argument("-r", "--radius", type=int, default=30, help="rayon en km autour de la ville (défaut : 30)")
    p.add_argument("-c", "--contract", action="append", choices=CONTRACTS, default=[],
                   help="type de contrat (répétable)")
    p.add_argument("--remote", action="store_true", help="télétravail uniquement (si la source le permet)")
    p.add_argument("--age", choices=AGE_CHOICES, help="ancienneté maximale de l'offre")
    p.add_argument("-n", "--limit", type=int, default=50, help="nombre max d'offres par source (défaut : 50)")
    p.add_argument("-s", "--source", action="append", choices=list(SOURCES), default=[],
                   help="limiter à certaines sources (répétable ; défaut : toutes)")
    p.add_argument("-x", "--exclude", action="append", choices=list(SOURCES), default=[],
                   help="exclure une source (répétable)")
    p.add_argument("-o", "--output", type=Path,
                   help="fichier de sortie ; le format est déduit de l'extension (.html, .json, .csv)")
    p.add_argument("-f", "--format", choices=("table", "json", "csv", "html"),
                   help="format d'affichage sur la sortie standard (défaut : table)")
    p.add_argument("--no-dedup", action="store_true", help="ne pas fusionner les doublons entre sites")
    p.add_argument("--list-sources", action="store_true", help="lister les sources et leur état")
    p.add_argument("-v", "--verbose", action="store_true", help="journal détaillé")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def list_sources() -> str:
    lines = []
    for name, cls in SOURCES.items():
        src = cls()
        if not src.is_configured():
            state = "non configurée (clé API requise, voir README)"
        elif name == "francetravail":
            state = "API officielle" if src.use_api else "scraping du site (clé API conseillée, voir README)"
        else:
            state = "prête"
        lines.append(f"  {name:<14} {cls.label:<24} {state}")
    return "Sources disponibles :\n" + "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.list_sources:
        print(list_sources())
        return 0
    if not args.keywords:
        build_parser().error("indiquez des mots-clés, ex. : jobagg \"développeur python\" -l Paris")

    names = args.source or list(SOURCES)
    names = [n for n in names if n not in args.exclude]
    if not args.source:  # par défaut, on saute silencieusement les sources non configurées
        names = [n for n in names if SOURCES[n]().is_configured()]

    q = SearchQuery(
        keywords=args.keywords,
        location=args.location,
        radius_km=args.radius,
        contracts=sorted(set(args.contract)),
        remote=args.remote,
        max_age_days=AGE_CHOICES.get(args.age) if args.age else None,
        limit=args.limit,
    )

    tty = sys.stderr.isatty()

    def progress(rep: SourceReport) -> None:
        status = f"✗ {rep.error}" if rep.error else f"✓ {rep.count} offre(s)"
        print(f"  {rep.label:<24} {status}  ({rep.seconds:.1f} s)", file=sys.stderr)

    print(f"Recherche « {q.keywords} »" + (f" à {q.location}" if q.location else "")
          + f" sur {len(names)} source(s)…", file=sys.stderr)
    result = search(q, names, dedup=not args.no_dedup, on_progress=progress)
    print(f"→ {len(result.offers)} offre(s) au total"
          + (f", {result.duplicates_merged} doublon(s) fusionné(s)" if result.duplicates_merged else ""),
          file=sys.stderr)

    renderers = {"json": to_json, "csv": to_csv, "html": to_html}
    if args.output:
        fmt = args.output.suffix.lower().lstrip(".")
        if fmt not in renderers:
            print(f"Extension inconnue « .{fmt} » (attendu : .html, .json, .csv)", file=sys.stderr)
            return 2
        args.output.write_text(renderers[fmt](result), encoding="utf-8")
        print(f"Résultats enregistrés dans {args.output}", file=sys.stderr)

    fmt = args.format or (None if args.output else "table")
    if fmt == "table":
        if result.offers:
            print(to_table(result, color=sys.stdout.isatty() and tty))
    elif fmt:
        sys.stdout.write(renderers[fmt](result))

    ok = any(not r.error for r in result.reports)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
