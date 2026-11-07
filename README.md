# jobagg – agrégateur d'offres d'emploi françaises

Une seule commande pour chercher **en même temps** sur :

| Source | Méthode | Clé requise |
|---|---|---|
| **LinkedIn** | API publique « guest » (sans connexion) | non |
| **HelloWork** | page de résultats (+ repli sur les données schema.org) | non |
| **Welcome to the Jungle** | index de recherche Algolia public du site | non |
| **France Travail** | API officielle *Offres d'emploi v2*, ou scraping du site à défaut | conseillée (gratuite) |
| **APEC** (offres cadres) | web service JSON du site | non |
| **Adzuna** (agrège Indeed, Monster, sites carrière…) | API officielle | oui (gratuite) |

Les requêtes partent en parallèle, puis les résultats sont filtrés, **dédoublonnés** (une même offre publiée sur
plusieurs sites n'apparaît qu'une fois, avec la liste des sites) et triés du plus récent au plus ancien.
Une source en panne ou bloquée n'empêche pas les autres de répondre.

## Installation

Python 3.9 ou plus récent.

```bash
git clone https://github.com/JordanLako/agregateur-offres-emploi.git
```

```bash
cd agregateur-offres-emploi && pip install -e .
```

### Clés API (facultatif, recommandé)

```bash
cp .env.example .env
```

Puis remplissez `.env` :

- **France Travail** : créez une application sur <https://francetravail.io> et abonnez-la à l'API
  « Offres d'emploi v2 ». Renseignez `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET`.
  Sans ces clés, l'outil lit le site candidat.francetravail.fr, ce qui est moins fiable.
- **Adzuna** : créez un compte sur <https://developer.adzuna.com>, puis renseignez `ADZUNA_APP_ID` et
  `ADZUNA_APP_KEY`. Sans clés, Adzuna est simplement ignoré.

`jobagg --list-sources` affiche l'état de chaque source.

## Utilisation

```bash
jobagg "développeur python" -l Lyon
```

```bash
jobagg "data analyst" -l Paris -r 20 -c cdi -c cdd --age semaine -o offres.html
```

```bash
jobagg "chargé de communication" -l 33 -c alternance -s hellowork -s wttj -s francetravail
```

```bash
jobagg "infirmier" -l Nantes --format csv > offres.csv
```

| Option | Rôle |
|---|---|
| `-l`, `--location` | ville, code postal ou numéro de département |
| `-r`, `--radius` | rayon en km (défaut : 30) |
| `-c`, `--contract` | `cdi`, `cdd`, `stage`, `alternance`, `interim`, `freelance` (répétable) |
| `--remote` | télétravail uniquement (LinkedIn, HelloWork, WTTJ) |
| `--age` | `24h`, `3j`, `semaine`, `mois` |
| `-n`, `--limit` | nombre max d'offres **par source** (défaut : 50) |
| `-s`, `--source` / `-x`, `--exclude` | choisir ou exclure des sources : `linkedin`, `hellowork`, `wttj`, `francetravail`, `apec`, `adzuna` |
| `-o`, `--output` | fichier `.html`, `.json` ou `.csv` |
| `-f`, `--format` | sortie standard en `table` (défaut), `json`, `csv` ou `html` |
| `--no-dedup` | garder les doublons entre sites |
| `-v` | journal détaillé (utile quand une source ne renvoie rien) |

Le **rapport HTML** (`-o offres.html`) est une page autonome, à ouvrir dans un navigateur. On peut y filtrer
par texte, cocher ou décocher des sources et trier les colonnes.

Le fichier **CSV** utilise `;` comme séparateur et s'ouvre directement dans Excel ou LibreOffice.

### Depuis Python

```python
from jobagg.aggregator import search
from jobagg.models import SearchQuery

res = search(SearchQuery("comptable", location="Bordeaux", contracts=["cdi"], max_age_days=7))
for o in res.offers:
    print(o.published_at, o.source, o.title, o.company, o.url)
```

## Ajouter une plateforme

Créez `jobagg/sources/ma_source.py` avec une classe qui hérite de `Source` et implémente
`iter_offers(query)`, qui produit des `JobOffer`. Ajoutez-la ensuite au dictionnaire `SOURCES` dans
`jobagg/sources/__init__.py`. Les autres connecteurs servent de modèles.

Pistes pour d'autres plateformes françaises : Indeed (protection anti-robot forte : passez plutôt par Adzuna),
Cadremploi, Meteojob, JobTeaser, Jobijoba, Choisir le service public, Talent.com.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

Les tests tournent hors ligne, sur des extraits qui reproduisent le format de chaque plateforme.

## Limites à connaître

- **Fragilité** : LinkedIn, HelloWork et le repli France Travail lisent le HTML des sites. Si un site change
  sa mise en page, le connecteur concerné renvoie 0 offre ou une erreur, sans bloquer les autres. Il faut
  alors mettre à jour ses sélecteurs CSS. Les API officielles (France Travail, Adzuna) sont les plus stables.
- **Blocages** : en cas de requêtes trop nombreuses, LinkedIn répond par des erreurs 429 ou 999. L'outil
  espace ses requêtes et réessaie, mais gardez `--limit` raisonnable.
- **Welcome to the Jungle** : la clé Algolia publique du site peut changer. Si c'est le cas, récupérez la
  nouvelle dans l'onglet Réseau du navigateur (requêtes vers `*.algolia.net`) et renseignez
  `WTTJ_ALGOLIA_API_KEY`.
- **Filtres** : chaque site ne gère pas tous les filtres. Le type de contrat et l'ancienneté sont donc
  revérifiés après coup sur toutes les offres. Une offre dont le contrat ou la date est inconnu est conservée.
- **Conditions d'utilisation** : le scraping peut être contraire aux CGU de certains sites. Réservez cet outil
  à un usage personnel et modéré de recherche d'emploi.
