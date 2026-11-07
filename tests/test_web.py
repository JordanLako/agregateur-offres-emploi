import json
import threading
import urllib.error
import urllib.request
from datetime import timedelta

import pytest

from jobagg import web
from jobagg.models import JobOffer
from jobagg.sources.base import Source, SourceUnavailable
from jobagg.utils import now


class FakeA(Source):
    name, label, delay = "linkedin", "LinkedIn", 0

    def iter_offers(self, q):
        yield JobOffer("linkedin", "1", f"Développeur {q.keywords} (H/F)", "Acme", "Lyon", "https://e/1",
                       contract="CDI", published_at=now() - timedelta(days=1))
        yield JobOffer("linkedin", "2", "Stagiaire data", "Beta", "Lyon", "https://e/2", contract="Stage")


class FakeB(Source):
    name, label, delay = "hellowork", "HelloWork", 0

    def iter_offers(self, q):
        yield JobOffer("hellowork", "9", f"Developpeur {q.keywords} F/H", "ACME", "Lyon 3e", "https://e/9",
                       contract="CDI", salary="45 k€", published_at=now())


class FakeKo(Source):
    name, label, delay = "wttj", "Welcome to the Jungle", 0

    def iter_offers(self, q):
        raise SourceUnavailable("bloqué (HTTP 403)")
        yield  # pragma: no cover


FAKES = {"linkedin": FakeA, "hellowork": FakeB, "wttj": FakeKo}


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(web.Handler, "source_factory", staticmethod(lambda n: FAKES[n]()))
    monkeypatch.setattr(web.Handler, "status_provider", staticmethod(
        lambda: [{"name": n, "label": c.label, "configured": True, "note": ""} for n, c in FAKES.items()]))
    srv = web.make_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.headers.get("Content-Type"), r.read().decode()


def _events(body):
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_index_and_sources(server):
    code, ctype, body = _get(server + "/")
    assert code == 200 and "text/html" in ctype and "jobagg" in body
    _, _, body = _get(server + "/api/sources")
    assert [s["name"] for s in json.loads(body)] == ["linkedin", "hellowork", "wttj"]


def test_search_stream(server):
    qs = "keywords=python&location=Lyon&contract=cdi&source=linkedin&source=hellowork&source=wttj"
    code, ctype, body = _get(server + "/api/search?" + qs)
    assert code == 200 and ctype.startswith("text/event-stream")
    ev = _events(body)
    sources = {d["source"]: d for k, d in ev if k == "source"}
    assert sources["linkedin"]["count"] == 2 and sources["wttj"]["error"] == "bloqué (HTTP 403)"
    kind, done = ev[-1]
    assert kind == "done"
    # le stage est filtré (CDI demandé) et les deux annonces Acme sont fusionnées
    assert done["count"] == 1 and done["duplicates"] == 1
    assert done["offers"][0]["also_on"] == ["linkedin"]


def test_search_requires_keywords(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(server + "/api/search?location=Lyon")
    assert e.value.code == 400


def test_query_from_params_bounds():
    q, names = web.query_from_params({"keywords": ["x"], "radius": ["999"], "limit": ["0"], "age": ["7"],
                                      "contract": ["cdi", "bidon"], "source": ["inconnue"], "remote": ["1"]})
    assert (q.radius_km, q.limit, q.max_age_days, q.contracts, q.remote) == (200, 1, 7, ["cdi"], True)
    assert "linkedin" in names  # source inconnue ignorée -> toutes
