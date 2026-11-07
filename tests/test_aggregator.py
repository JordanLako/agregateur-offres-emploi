from datetime import timedelta

from jobagg import aggregator
from jobagg.cli import main
from jobagg.export import to_csv, to_html, to_json, to_table
from jobagg.models import JobOffer, SearchQuery
from jobagg.sources.base import Source, SourceUnavailable
from jobagg.utils import normalize, now, parse_date


def test_parse_date_relative():
    ref = now()
    assert (ref - parse_date("il y a 3 jours", ref)).days == 3
    assert (ref - parse_date("Publié hier", ref)).days == 1
    assert (ref - parse_date("2 weeks ago", ref)).days == 14
    assert parse_date("Aujourd'hui", ref) == ref
    assert parse_date("15/10/2026").month == 10
    assert parse_date("n'importe quoi") is None


def test_normalize_strips_gender_marks():
    assert normalize("Développeur Python (H/F)") == normalize("developpeur python F/H") == "developpeur python"


def test_deduplicate_merges_across_sources():
    d = now()
    a = JobOffer("linkedin", "1", "Développeur Python (H/F)", "Acme SAS", "Lyon", published_at=d - timedelta(days=2))
    b = JobOffer("hellowork", "2", "Developpeur Python F/H", "ACME", "Lyon", salary="45 k€",
                 description="desc", published_at=d)
    c = JobOffer("wttj", "3", "Data Engineer", "Acme", "Lyon")
    merged, n = aggregator.deduplicate([a, b, c])
    assert n == 1 and len(merged) == 2
    best = next(o for o in merged if o.title.startswith("Dev"))
    assert best.source == "hellowork" and best.also_on == ["linkedin"]


def test_filters():
    o = JobOffer("x", "1", "t", contract="Stage - 6 mois")
    assert aggregator.matches_contract(o, ["stage"])
    assert not aggregator.matches_contract(o, ["cdi"])
    assert aggregator.matches_contract(JobOffer("x", "2", "t"), ["cdi"])  # contrat inconnu : conservé
    old = JobOffer("x", "3", "t", published_at=now() - timedelta(days=40))
    assert not aggregator.is_recent(old, 30) and aggregator.is_recent(old, None)


class FakeOk(Source):
    name, label, delay = "ok", "Fake OK", 0

    def iter_offers(self, q):
        for i in range(10):
            yield JobOffer("ok", str(i), f"Poste {i}", "Boîte", "Paris", url=f"https://e/{i}",
                           published_at=now() - timedelta(days=i))


class FakeKo(Source):
    name, label, delay = "ko", "Fake KO", 0

    def iter_offers(self, q):
        raise SourceUnavailable("bloqué")
        yield  # pragma: no cover


def test_search_parallel_with_failing_source():
    res = aggregator.search(SearchQuery("x", limit=5, max_age_days=3), ["ok", "ko"],
                            source_factory=lambda n: {"ok": FakeOk, "ko": FakeKo}[n]())
    assert [r.count for r in res.reports] == [5, 0]
    assert res.reports[1].error == "bloqué"
    assert len(res.offers) == 4  # 5 offres, dont une de plus de 3 jours
    assert res.offers[0].source_id == "0"  # tri du plus récent au plus ancien

    assert '"count": 4' in to_json(res)
    assert to_csv(res).splitlines()[0].lstrip("﻿").startswith("source;")
    html = to_html(res)
    assert "Poste 0" in html and "bloqué" in html
    assert "Poste 3" in to_table(res, color=False)


def test_cli_list_sources(capsys):
    assert main(["--list-sources"]) == 0
    out = capsys.readouterr().out
    for name in ("linkedin", "hellowork", "wttj", "francetravail", "apec", "adzuna"):
        assert name in out
