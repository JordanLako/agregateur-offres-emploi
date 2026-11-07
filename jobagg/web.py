"""Version web : `jobagg-web` puis ouvrir http://localhost:8000.

Serveur sans dépendance externe (bibliothèque standard). La page envoie la recherche à
/api/search, qui renvoie un flux SSE : un événement par source dès qu'elle a répondu,
puis les résultats fusionnés.
"""

from __future__ import annotations

import argparse
import json
import logging
import queue
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from . import __version__
from .aggregator import SourceReport, search
from .cli import load_dotenv
from .models import CONTRACTS, SearchQuery
from .sources import SOURCES, Source

log = logging.getLogger("jobagg")

AGES = {"1": 1, "3": 3, "7": 7, "30": 30}


def query_from_params(params: dict[str, list[str]]) -> tuple[SearchQuery, list[str]]:
    def one(name: str, default: str = "") -> str:
        return (params.get(name) or [default])[0].strip()

    keywords = one("keywords")
    if not keywords:
        raise ValueError("Indiquez des mots-clés.")
    try:
        radius = max(0, min(200, int(one("radius", "30") or 30)))
        limit = max(1, min(200, int(one("limit", "50") or 50)))
    except ValueError:
        raise ValueError("Rayon et nombre d'offres doivent être des nombres.")
    contracts = sorted({c for c in params.get("contract", []) if c in CONTRACTS})
    names = [s for s in params.get("source", []) if s in SOURCES] or list(SOURCES)
    q = SearchQuery(
        keywords=keywords,
        location=one("location"),
        radius_km=radius,
        contracts=contracts,
        remote=one("remote") in ("1", "true", "on"),
        max_age_days=AGES.get(one("age")),
        limit=limit,
    )
    return q, names


def sources_status() -> list[dict]:
    out = []
    for name, cls in SOURCES.items():
        src = cls()
        note = ""
        if not src.is_configured():
            note = "Clé API manquante (voir README)"
        elif name == "francetravail" and not getattr(src, "use_api", False):
            note = "Sans clé API : lecture du site, moins fiable"
        out.append({"name": name, "label": cls.label, "configured": src.is_configured(), "note": note})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = f"jobagg/{__version__}"
    #: remplaçable dans les tests
    source_factory: Callable[[str], Source] = staticmethod(lambda n: SOURCES[n]())
    status_provider: Callable[[], list[dict]] = staticmethod(sources_status)

    def log_message(self, fmt, *args):  # journal discret
        log.info("%s - %s", self.address_string(), fmt % args)

    # --- utilitaires ------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, extra: Optional[dict] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    # --- routes -----------------------------------------------------------
    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            page = resources.files("jobagg").joinpath("static/index.html").read_bytes()
            self._send(200, page, "text/html; charset=utf-8")
        elif url.path == "/api/sources":
            self._json(self.status_provider())
        elif url.path == "/api/search":
            self._search_stream(params)
        else:
            self._send(404, b"Page introuvable", "text/plain; charset=utf-8")

    def _run(self, params, on_progress=None):
        q, names = query_from_params(params)
        return search(q, names, on_progress=on_progress, source_factory=self.source_factory)

    def _search_stream(self, params) -> None:
        try:
            query_from_params(params)
        except ValueError as e:
            self._json({"error": str(e)}, HTTPStatus.BAD_REQUEST)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        events: "queue.Queue[tuple[str, object]]" = queue.Queue()

        def progress(rep: SourceReport) -> None:
            events.put(("source", rep.__dict__))

        def worker() -> None:
            try:
                res = self._run(params, progress)
                events.put(("done", {
                    "count": len(res.offers),
                    "duplicates": res.duplicates_merged,
                    "offers": [o.to_dict() for o in res.offers],
                }))
            except Exception as e:  # pragma: no cover - garde-fou
                log.exception("Recherche impossible")
                events.put(("fail", {"error": str(e)}))

        threading.Thread(target=worker, daemon=True).start()
        while True:
            try:
                kind, data = events.get(timeout=15)
            except queue.Empty:
                kind, data = "ping", {}
            try:
                payload = json.dumps(data, ensure_ascii=False)
                self.wfile.write(f"event: {kind}\ndata: {payload}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return  # l'utilisateur a fermé la page ou relancé une recherche
            if kind in ("done", "fail"):
                return


def make_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="jobagg-web", description="Interface web de jobagg")
    p.add_argument("--host", default="127.0.0.1",
                   help="adresse d'écoute (0.0.0.0 pour l'ouvrir au réseau local ; défaut : 127.0.0.1)")
    p.add_argument("-p", "--port", type=int, default=8000, help="port (défaut : 8000)")
    p.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur automatiquement")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    srv = make_server(args.host, args.port)
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{srv.server_port}"
    print(f"jobagg web lancé sur {url}  (Ctrl+C pour arrêter)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
