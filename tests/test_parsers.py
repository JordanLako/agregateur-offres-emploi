"""Tests des parseurs à partir d'extraits reproduisant le format de chaque plateforme."""

from jobagg.models import SearchQuery
from jobagg.sources import adzuna, apec, francetravail, hellowork, linkedin, wttj

LINKEDIN_HTML = """
<li><div class="base-card job-search-card" data-entity-urn="urn:li:jobPosting:4012345678">
  <a class="base-card__full-link" href="https://fr.linkedin.com/jobs/view/dev-python-at-acme-4012345678?refId=x"></a>
  <h3 class="base-search-card__title"> Développeur Python (H/F) </h3>
  <h4 class="base-search-card__subtitle"><a>Acme</a></h4>
  <span class="job-search-card__location">Lyon, Auvergne-Rhône-Alpes, France</span>
  <span class="job-search-card__salary-info">45 000 € - 55 000 €</span>
  <time class="job-search-card__listdate" datetime="2026-11-01">il y a 6 jours</time>
</div></li>
<li><div class="base-card" data-entity-urn="urn:li:jobPosting:999">
  <h3 class="base-search-card__title">********</h3><h4 class="base-search-card__subtitle">****</h4>
</div></li>
"""

HELLOWORK_HTML = """
<ul><li data-id-storage-item-id="61234567">
  <input type="hidden" name="title" value="Data Analyst H/F">
  <input type="hidden" name="company" value="Banque Exemple">
  <a href="/fr-fr/emplois/61234567.html"><h3><p>Data Analyst H/F</p></h3></a>
  <div class="tw-tag-secondary-s">Lyon - 69</div>
  <div class="tw-tag-secondary-s">CDI</div>
  <div class="tw-tag-secondary-s">40 000 - 48 000 € / an</div>
  <div class="tw-text-grey-500">il y a 3 jours</div>
</li></ul>
"""

FT_HTML = """
<ul><li class="result" data-id-offre="198ABCD">
  <a href="/offres/recherche/detail/198ABCD"><h2 class="media-heading">
    <span class="media-heading-title">Technicien support (H/F)</span></h2></a>
  <p class="subtext">INFOSERV - 69 - LYON 03</p>
  <p class="description">Vous assurez le support de niveau 1…</p>
  <p class="contrat">CDI Temps plein</p>
  <p class="date">Publié hier</p>
</li></ul>
"""


def test_linkedin_parse_and_skip_masked():
    offers = linkedin.parse_cards(LINKEDIN_HTML)
    assert len(offers) == 1
    o = offers[0]
    assert o.source_id == "4012345678"
    assert o.title == "Développeur Python (H/F)"
    assert o.company == "Acme"
    assert o.url == "https://www.linkedin.com/jobs/view/4012345678/"
    assert o.published_at.date().isoformat() == "2026-11-01"
    assert "45 000" in o.salary


def test_linkedin_params():
    p = linkedin.build_params(SearchQuery("python", "Lyon", radius_km=40, contracts=["cdi", "stage"],
                                          remote=True, max_age_days=7), 20)
    assert p["start"] == 20 and p["f_JT"] == "F,I" and p["f_WT"] == "2"
    assert p["f_TPR"] == "r604800" and p["distance"] == 25


def test_hellowork_parse():
    (o,) = hellowork.parse_results(HELLOWORK_HTML)
    assert (o.source_id, o.title, o.company) == ("61234567", "Data Analyst H/F", "Banque Exemple")
    assert o.url == "https://www.hellowork.com/fr-fr/emplois/61234567.html"
    assert o.location == "Lyon - 69" and o.contract == "CDI" and "€" in o.salary
    assert o.published_at is not None


def test_hellowork_jsonld_fallback():
    html = """<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"item":
      {"@type":"JobPosting","title":"Comptable","url":"https://www.hellowork.com/fr-fr/emplois/777.html",
       "hiringOrganization":{"name":"Cabinet X"},"jobLocation":{"address":{"addressLocality":"Nantes"}},
       "datePosted":"2026-11-05"}}]}</script>"""
    (o,) = hellowork.parse_results(html)
    assert (o.source_id, o.company, o.location) == ("777", "Cabinet X", "Nantes")


def test_wttj_parse_and_body():
    data = {"nbPages": 1, "hits": [{
        "objectID": "abc", "reference": "REF1", "name": "Product Designer", "slug": "product-designer_paris",
        "organization": {"name": "Startup", "slug": "startup"}, "offices": [{"city": "Paris", "country": "France"}],
        "contract_type": "full_time", "remote": "partial", "salary_minimum": 50000, "salary_maximum": 60000,
        "salary_currency": "EUR", "salary_period": "yearly", "published_at": "2026-11-06T10:00:00Z",
        "summary": "Rejoignez-nous"}]}
    (o,) = wttj.parse_hits(data)
    assert o.source_id == "REF1" and o.contract == "CDI" and o.remote == "Télétravail partiel"
    assert o.url == "https://www.welcometothejungle.com/fr/companies/startup/jobs/product-designer_paris"
    assert o.salary == "50 000 – 60 000 EUR/an"
    body = wttj.build_body(SearchQuery("design", "Paris", radius_km=10, contracts=["cdi"], remote=True), 0,
                           (48.85, 2.35))
    assert body["aroundRadius"] == 10000 and "contract_type:full_time" in body["filters"]
    assert "remote:fulltime" in body["filters"]


def test_francetravail_api_and_html():
    data = {"resultats": [{"id": "201XYZ", "intitule": "Boulanger", "entreprise": {"nom": "Fournil"},
                           "lieuTravail": {"libelle": "33 - BORDEAUX"}, "typeContratLibelle": "CDD - 6 Mois",
                           "salaire": {"libelle": "Mensuel de 1900 Euros"}, "dateCreation": "2026-11-04T08:00:00.000Z"}]}
    (o,) = francetravail.parse_api(data)
    assert o.url.endswith("/detail/201XYZ") and o.company == "Fournil" and o.contract.startswith("CDD")
    p = francetravail.api_params(SearchQuery("boulanger", "33", contracts=["cdd", "alternance"], max_age_days=5),
                                 0, 50, None)
    assert p["departement"] == "33" and p["range"] == "0-49" and p["typeContrat"] == "CDD"
    assert p["publieeDepuis"] == 7 and "natureContrat" in p
    p = francetravail.api_params(SearchQuery("x", "Lyon"), 0, 50, {"code": "69123"})
    assert p["commune"] == "69123" and p["distance"] == 30

    (h,) = francetravail.parse_html(FT_HTML)
    assert (h.source_id, h.title, h.company, h.location) == ("198ABCD", "Technicien support (H/F)",
                                                              "INFOSERV", "69 - LYON 03")


def test_apec_parse():
    data = {"totalCount": 1, "resultats": [{"numeroOffre": "178901W", "intitule": "Chef de projet",
                                            "nomCommercial": "Conseil SA", "lieuTexte": "Lille - 59",
                                            "typeContrat": 101888, "salaireTexte": "55 - 65 k€ brut annuel",
                                            "datePublication": "2026-11-02T00:00:00.000+0000"}]}
    (o,) = apec.parse_results(data)
    assert o.contract == "CDI" and o.url.endswith("/detail-offre/178901W")
    assert o.published_at is not None


def test_adzuna_parse():
    data = {"count": 1, "results": [{"id": 42, "title": "Infirmier", "company": {"display_name": "Clinique"},
                                     "location": {"display_name": "Toulouse"}, "redirect_url": "https://x/42",
                                     "contract_type": "permanent", "salary_min": 30000, "salary_max": 30000,
                                     "salary_is_predicted": "1", "created": "2026-11-03T09:00:00Z"}]}
    (o,) = adzuna.parse_results(data)
    assert o.contract == "CDI" and o.salary.endswith("(estimé)")
