# Enterprise Data & IA Copilot

Plateforme SaaS de démonstration qui transforme un fichier CSV ou XLSX en espace d'analyse exploitable : indicateurs Pandas, audit Data Quality, graphiques interactifs, détection d'anomalies, assistant IA et rapports exportables.

Le projet est une application métier complète, pas un site vitrine. Toutes les valeurs affichées sont calculées par le backend FastAPI à partir du dataset actif.

## Fonctionnalités

- import sécurisé de fichiers CSV et XLSX (50 Mio par défaut, limite configurable) ;
- profilage Pandas et KPI adaptés aux colonnes disponibles ;
- score Data Quality explicable, valeurs manquantes, identifiants répétés, doublons signalés, types mixtes et valeurs extrêmes ;
- dashboard Recharts configurable par dimension, mesure et agrégation ;
- détection multivariée avec `IsolationForest` et `random_state=42` ;
- synthèse et questions en langage naturel via l'API OpenAI ;
- fallback local déterministe lorsqu'aucune clé OpenAI n'est fournie ou que l'API est indisponible ;
- génération et téléchargement de rapports Markdown ou HTML ;
- historique réel des opérations dans SQLite.

## Stack

| Couche | Technologies |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Lucide |
| Backend | FastAPI, Python, Pandas, NumPy, scikit-learn |
| IA | OpenAI Responses API avec fallback local |
| Persistance | SQLite pour l'historique, stockage local des imports et rapports |

## Architecture

```text
enterprise-data-ia-copilot/
├── frontend/
│   ├── app/                 # routes Next.js App Router
│   ├── components/          # shell SaaS, états et composants métier
│   ├── lib/                 # client HTTP typé et hooks
│   └── package.json
├── backend/
│   ├── main.py              # routes FastAPI
│   ├── src/                 # qualité, analytics, IA, anomalies, rapports
│   ├── data/
│   │   ├── samples/         # quatre datasets de démonstration
│   │   └── uploads/         # fichiers importés, ignorés par Git
│   ├── reports/             # exports générés, ignorés par Git
│   ├── tests/
│   └── requirements.txt
├── docs/screenshots/
└── README.md
```

Le backend charge `marketing_leads.csv` au démarrage pour permettre une démonstration immédiate. Un import remplace le dataset actif pour l'ensemble des pages. L'historique SQLite persiste entre les redémarrages ; le dataset actif, lui, revient à l'échantillon par défaut au redémarrage.

## Installation sous Windows

Prérequis : Python 3.10 ou plus récent, Node.js 20.9 ou plus récent et npm.

### Terminal 1 — backend

Depuis la racine du projet :

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt

Copy-Item .\backend\.env.example .\backend\.env
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

- API : `http://127.0.0.1:8000`
- Documentation interactive : `http://127.0.0.1:8000/docs`

### Terminal 2 — frontend

```powershell
Set-Location .\frontend
Copy-Item .\.env.example .\.env.local
npm install
npm run dev
```

Application : `http://localhost:3000`

Si votre réseau d'entreprise utilise son propre certificat et que npm échoue en TLS, relancez uniquement l'installation avec :

```powershell
$env:NODE_OPTIONS = '--use-system-ca'
npm install
```

## Configuration

`backend/.env` :

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
MAX_UPLOAD_BYTES=52428800
```

`frontend/.env.local` :

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

La clé OpenAI reste exclusivement côté serveur. Lorsqu'elle est active, seuls le schéma, les métadonnées, les KPI et les statistiques agrégées sont envoyés au modèle — jamais le fichier complet ni ses lignes brutes. L'appel Responses API utilise `store=False`. Sans clé, en cas de timeout, de quota ou de clé invalide, l'interface affiche explicitement le mode local.

## Exécution avec Docker Compose

Cette option lance le frontend et le backend dans deux conteneurs non privilégiés. Les imports, rapports et l'historique SQLite sont conservés dans le volume nommé `copilot-runtime` ; les datasets de démonstration restent intégrés à l'image backend.

```powershell
# Depuis la racine
Copy-Item .\.env.example .\.env
docker compose up --build -d
docker compose ps
```

- Application : `http://localhost:3000`
- API et documentation : `http://localhost:8000/docs`

Pour suivre les journaux puis arrêter la stack sans supprimer les données :

```powershell
docker compose logs -f
docker compose down
```

`PUBLIC_API_URL` est intégrée au bundle navigateur pendant le build Next.js. Si le port ou le domaine public du backend change, modifiez cette variable puis relancez `docker compose up --build -d`. La clé OpenAI, elle, est injectée uniquement à l'exécution dans le conteneur FastAPI.

Si le réseau d'entreprise inspecte les connexions TLS, placez uniquement ses certificats d'autorité racine publics au format PEM (`.crt`) dans `docker/certs/` avant le build. Ils sont ignorés par Git ; aucune clé privée ne doit être copiée dans ce dossier. La vérification TLS reste active.

## Routes frontend

| Route | Usage |
| --- | --- |
| `/` | vue opérationnelle et KPI du dataset actif |
| `/data-quality` | audit détaillé et priorités de correction |
| `/dashboard` | agrégations et graphiques interactifs |
| `/ai-assistant` | synthèse et questions sur les métriques calculées |
| `/anomalies` | résultats réels d'IsolationForest |
| `/reports` | génération, aperçu et téléchargement Markdown/HTML |
| `/history` | journal SQLite des opérations réalisées |

## API FastAPI

| Méthode | Endpoint | Résultat |
| --- | --- | --- |
| `POST` | `/api/upload` | valide, stocke et active un CSV/XLSX |
| `GET` | `/api/overview` | métadonnées, KPI et séries de synthèse |
| `GET` | `/api/data-quality` | score, contrôles par colonne et recommandations |
| `GET` | `/api/dashboard` | agrégation compatible Recharts |
| `POST` | `/api/ai-summary` | synthèse OpenAI ou locale |
| `POST` | `/api/ask` | réponse factuelle sur les agrégats disponibles |
| `GET` | `/api/anomalies` | lignes signalées par IsolationForest |
| `POST` | `/api/report` | rapport Markdown ou HTML réel |
| `GET` | `/api/history` | opérations persistées dans SQLite |

Un endpoint de santé est également disponible sur `GET /api/health`.

## Logique d'analyse

Le score Data Quality, borné entre 0 et 100, applique des pénalités déterministes : complétude (50 points), doublons ou identifiants répétés (25), valeurs extrêmes IQR (15), incohérences de type et valeurs infinies (10). Il sert à prioriser l'audit et ne remplace pas les règles métier.

Pour les anomalies, les colonnes numériques constantes sont exclues, les valeurs manquantes sont imputées par la médiane, puis les variables sont standardisées avant `IsolationForest`. Le score affiché classe les observations ; il ne représente ni une probabilité ni une causalité.

## Tests et qualité

```powershell
# Depuis la racine
& .\.venv\Scripts\python.exe -m pytest .\backend\tests -q

Set-Location .\frontend
npm run typecheck
npm run lint
npm run build
```

La suite backend utilise des répertoires et une base SQLite temporaires. Elle couvre notamment les dimensions des données, l'audit qualité, les agrégations, les imports CSV/XLSX, la sécurité des fichiers, le fallback IA, les anomalies et les rapports.

### Parcours E2E avec Robot Framework

La suite Robot démarre automatiquement une stack isolée sur les ports `3100` et `8100`, pilote Chrome en mode headless, importe un vrai CSV et parcourt les sept pages. Les éventuels serveurs déjà ouverts sur `3000` et `8000` ne sont pas modifiés.

Les uploads, rapports et événements SQLite du parcours E2E sont écrits dans `tests/robot/results/runtime/`. Le run recrée cet espace avant chaque exécution : il ne modifie donc pas les données locales de démonstration du backend.

Le parcours comporte 12 scénarios : workflow nominal complet, XLSX corrompu, atomicité de l'import, détection non applicable, dataset entièrement numérique et indisponibilité de l'API.

```powershell
# Depuis la racine du projet
python -m pip install -r .\tests\robot\requirements.txt
python -m robot --outputdir .\tests\robot\results .\tests\robot\enterprise_data_ia.robot
```

Les preuves d'exécution sont générées dans `tests/robot/results/` : `report.html`, `log.html`, `output.xml`, journaux FastAPI/Next.js et captures automatiques en cas d'échec.

### Intégration continue

Le workflow GitHub Actions [`.github/workflows/ci.yml`](.github/workflows/ci.yml) exécute automatiquement Pytest, le contrôle TypeScript, ESLint, le build Next.js et les 12 scénarios Robot Framework. Les rapports E2E sont conservés comme artefact de CI pendant 14 jours, y compris lorsqu'un scénario échoue.

## Scénario de démonstration en entretien

1. Ouvrir la vue d'ensemble sur l'échantillon Marketing Leads.
2. Importer `backend/data/samples/packaging_data.csv` depuis la topbar.
3. Montrer que le contexte passe réellement à 12 lignes et 10 colonnes sur toutes les vues.
4. Expliquer le score Data Quality puis modifier dimension, mesure et agrégation dans le dashboard.
5. Relancer IsolationForest et examiner les colonnes contributrices d'une anomalie.
6. Poser une question à l'assistant, en montrant le badge OpenAI ou fallback local.
7. Générer un rapport HTML, le télécharger, puis retrouver l'opération dans l'historique SQLite.

## Captures d'écran

Les captures ci-dessous proviennent de l'application Docker réelle avec le dataset Marketing Leads, en 1440 × 900.

### Vue d'ensemble

![Vue d'ensemble du dataset actif](docs/screenshots/overview.png)

### Audit Data Quality

![Audit Data Quality](docs/screenshots/data-quality.png)

### Dashboard métier

![Dashboard Recharts configurable](docs/screenshots/dashboard.png)

### Détection d'anomalies

![Résultat IsolationForest](docs/screenshots/anomalies.png)

## Limites assumées

Docker Compose rend l'exécution reproductible, mais ne remplace pas une plateforme de production publique : TLS, authentification, sauvegardes automatisées et orchestration distribuée restent à ajouter avant une exposition Internet.

Cette version est une application locale démontrable. Elle n'implémente pas encore l'authentification, le multi-tenant, un stockage objet cloud, une file de tâches ni le déploiement distribué. Les imports, rapports et événements SQLite sont conservés localement sans purge automatique ; en usage prolongé, il faut donc définir une politique de rétention ou nettoyer périodiquement `backend/data/uploads/`, `backend/reports/` et `backend/data/history.db`. Ces fonctions d'exploitation ne sont ni simulées dans l'interface ni revendiquées comme disponibles.
