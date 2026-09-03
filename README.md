# Enterprise Data & IA Copilot

Plateforme SaaS de démonstration qui transforme un fichier CSV ou XLSX en espace d'analyse exploitable : indicateurs Pandas, audit Data Quality, graphiques interactifs, détection d'anomalies, assistant IA et rapports exportables.

Le projet est une application métier complète, pas un site vitrine. Toutes les valeurs affichées sont calculées par le backend FastAPI à partir du dataset actif.

[Démo en ligne](https://rare-communication-production.up.railway.app) · [CI GitHub Actions](https://github.com/benjAttack667/enterprise-data-ia-copilot/actions)

La démo publique est protégée par un mot de passe partagé. Elle doit être utilisée uniquement avec les datasets synthétiques fournis : ne téléversez aucune donnée personnelle ou confidentielle.

## Fonctionnalités

- import CSV (virgule, point-virgule ou tabulation) et XLSX streamé et borné à 10 Mio, sans copie complète du fichier en mémoire ;
- détection déterministe du séparateur CSV et sélection explicite de la feuille pour les classeurs Excel multi-feuilles ;
- quotas configurables à la baisse sur les lignes, colonnes, cellules et archives Excel, avec plafonds de sécurité et limitation de fréquence ;
- jauge réelle du stockage utilisé et rétention automatique des imports, rapports et événements ;
- accès de démonstration protégé par une session HTTP-only signée et une API FastAPI non exposée directement au navigateur ;
- profilage Pandas avec types sémantiques, KPI adaptés et conversion analytique non destructive des nombres stockés en texte ;
- score Data Quality explicable, chaînes vides, valeurs manquantes, dates invalides ou ambiguës, identifiants répétés, doublons signalés, types mixtes et valeurs extrêmes ;
- dashboard Recharts configurable par dimension, mesure et agrégation ;
- détection multivariée avec `IsolationForest`, exclusion des identifiants, gestion robuste des valeurs absentes et `random_state=42` ;
- synthèse et questions en langage naturel via l'API OpenAI ;
- fallback local déterministe lorsqu'aucune clé OpenAI n'est fournie ou que l'API est indisponible ;
- quota global des appels IA, limite de sortie et télémétrie persistante des tokens/coûts estimés sans conserver les questions ni les réponses ;
- cache LRU borné des analyses Pandas et IsolationForest, isolé par dataset et paramètres ;
- génération et téléchargement de rapports Markdown ou HTML ;
- historique réel des opérations dans SQLite.

## Stack

| Couche | Technologies |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Lucide |
| Backend | FastAPI, Python, Pandas, NumPy, scikit-learn |
| IA | OpenAI Responses API avec fallback local |
| Persistance | SQLite pour l'historique, stockage local des imports et rapports |

Le navigateur communique uniquement avec le proxy same-origin Next.js. Après validation de la session, ce proxy ajoute côté serveur un jeton privé pour joindre FastAPI. Le mot de passe, le secret de session et le jeton backend ne sont jamais intégrés au bundle navigateur.

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

Le backend charge `marketing_leads.csv` lorsqu'aucun import restaurable n'existe, afin de permettre une démonstration immédiate. Un import remplace le dataset actif pour l'ensemble des pages. Le fichier, son empreinte SHA-256 et ses métadonnées sont conservés sur le volume dans un manifeste atomique : après un redémarrage, le même dataset et la même feuille Excel redeviennent actifs. Si un fichier importé subsiste sans manifeste ou si cet état est invalide, l'application reste disponible sur l'échantillon et affiche explicitement le repli au lieu d'activer arbitrairement un fichier.

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
COPILOT_ENVIRONMENT=local
BACKEND_SERVICE_TOKEN=<jeton-aléatoire-identique-au-frontend>
API_DOCS_ENABLED=true

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=600
AI_RATE_LIMIT_REQUESTS=20
AI_RATE_LIMIT_WINDOW_SECONDS=600
MAX_AI_USAGE_ENTRIES=1000
ANALYSIS_CACHE_MAX_ENTRIES=32
ANALYSIS_CACHE_MAX_BYTES=8388608
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
MAX_UPLOAD_BYTES=10485760
MAX_DATASET_ROWS=100000
MAX_DATASET_COLUMNS=200
MAX_DATASET_CELLS=2000000
MAX_XLSX_UNCOMPRESSED_BYTES=52428800
MAX_XLSX_COMPRESSION_RATIO=100
MAX_XLSX_ENTRIES=1000
UPLOAD_RATE_LIMIT_REQUESTS=10
UPLOAD_RATE_LIMIT_WINDOW_SECONDS=600
MAX_REPORT_FILES=20
MAX_HISTORY_ENTRIES=500
```

`frontend/.env.local` :

```dotenv
BACKEND_INTERNAL_URL=http://127.0.0.1:8000
BACKEND_SERVICE_TOKEN=<jeton-aléatoire-identique-au-backend>
DEMO_ACCESS_PASSWORD=<mot-de-passe-fort>
SESSION_SECRET=<secret-aléatoire-de-32-octets-minimum>
```

Générez séparément le jeton backend et le secret de session avec `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Utilisez une troisième valeur forte comme mot de passe de démonstration. Ne commitez jamais ces valeurs.

La clé OpenAI reste exclusivement côté serveur. Lorsqu'elle est active, la question utilisateur, le schéma, les métadonnées, les KPI et les statistiques agrégées sont envoyés au modèle — jamais le fichier complet ni ses lignes brutes. L'appel Responses API utilise `store=False` et borne la sortie à `OPENAI_MAX_OUTPUT_TOKENS`. Sans clé, en cas de timeout, de quota ou de clé invalide, l'interface affiche explicitement le mode local.

Les compteurs proviennent du champ `usage` de la [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/retrieve). Pour le modèle par défaut `gpt-4.1-mini`, l'application estime le coût avec les [tarifs officiels du modèle](https://developers.openai.com/api/docs/models/gpt-4.1-mini) : entrée non cachée, entrée cachée et sortie sont comptées séparément. Ce montant est une estimation applicative des réponses mesurées, pas une facture OpenAI. Un modèle sans tarif enregistré ou un appel interrompu conserve ses tokens/coûts à `null` au lieu d'inventer un montant. SQLite ne reçoit que l'opération, le fournisseur, le modèle, les compteurs et le coût estimé — jamais le prompt, la question, les agrégats ou la réponse.

## Exécution avec Docker Compose

Cette option lance le frontend et le backend dans deux conteneurs non privilégiés. Les imports, rapports et l'historique SQLite sont conservés dans le volume nommé `copilot-runtime` ; les datasets de démonstration restent intégrés à l'image backend.

```powershell
# Depuis la racine
Copy-Item .\.env.example .\.env
# Remplissez BACKEND_SERVICE_TOKEN, DEMO_ACCESS_PASSWORD et SESSION_SECRET
# avec trois secrets différents avant le premier démarrage.
docker compose up --build -d
docker compose ps
```

- Application : `http://localhost:3000`
- Documentation locale, si `API_DOCS_ENABLED=true` : `http://localhost:8000/docs`

Pour suivre les journaux puis arrêter la stack sans supprimer les données :

```powershell
docker compose logs -f
docker compose down
```

Les quatre variables de sécurité frontend sont injectées uniquement à l'exécution dans le serveur Next.js. Aucune variable `NEXT_PUBLIC_*` ne contient un secret. Dans Docker Compose, Next.js contacte FastAPI sur le réseau interne via `http://backend:8000`.

Si le réseau d'entreprise inspecte les connexions TLS, placez uniquement ses certificats d'autorité racine publics au format PEM (`.crt`) dans `docker/certs/` avant le build. Ils sont ignorés par Git ; aucune clé privée ne doit être copiée dans ce dossier. La vérification TLS reste active.

## Déploiement Railway sécurisé

Configurez les variables suivantes avant de déployer cette version. La présence de `RAILWAY_PROJECT_ID` place automatiquement le backend en mode production ; il refuse volontairement de démarrer si son jeton est absent ou fait moins de 32 octets.

Service backend :

```dotenv
COPILOT_ENVIRONMENT=production
BACKEND_SERVICE_TOKEN=<secret-aléatoire-partagé-avec-le-frontend>
API_DOCS_ENABLED=false
```

Service frontend :

```dotenv
BACKEND_INTERNAL_URL=http://<nom-du-service-backend>.railway.internal:8000
BACKEND_SERVICE_TOKEN=<même-secret-que-le-backend>
DEMO_ACCESS_PASSWORD=<mot-de-passe-fort-à-communiquer-aux-recruteurs>
SESSION_SECRET=<autre-secret-aléatoire-de-32-octets-minimum>
```

Utilisez une variable partagée Railway pour `BACKEND_SERVICE_TOKEN` afin d'éviter toute divergence. Le domaine public du backend peut rester disponible pour le healthcheck, mais toutes les routes métier répondent `401` sans ce jeton. `/api/health` reste public et ne divulgue aucune information sur le dataset.

## Routes frontend

| Route | Usage |
| --- | --- |
| `/login` | authentification de la démo et création de la session HTTP-only |
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
| `POST` | `/api/upload` | valide, stocke et active un CSV/XLSX (`sheet_name` optionnel pour Excel) |
| `GET` | `/api/overview` | métadonnées, KPI et séries de synthèse |
| `GET` | `/api/data-quality` | score, contrôles par colonne et recommandations |
| `GET` | `/api/dashboard` | agrégation compatible Recharts |
| `POST` | `/api/ai-summary` | synthèse OpenAI ou locale |
| `POST` | `/api/ask` | réponse factuelle sur les agrégats disponibles |
| `GET` | `/api/ai-usage` | quota de l'instance et télémétrie IA persistée sans contenu utilisateur |
| `GET` | `/api/anomalies` | lignes signalées par IsolationForest |
| `POST` | `/api/report` | rapport Markdown ou HTML réel |
| `GET` | `/api/history` | opérations persistées dans SQLite |

Un endpoint de santé minimal reste public sur `GET /api/health`. Toutes les autres routes FastAPI exigent le jeton `Authorization: Bearer <BACKEND_SERVICE_TOKEN>` ajouté par le proxy Next.js ; le navigateur ne possède jamais ce jeton. La documentation FastAPI est désactivée par défaut en production.

Un garde ASGI vérifie le jeton de service et la taille du corps avant que FastAPI ne parse le JSON ou le multipart, y compris lorsque `Content-Length` est absent ou mensonger. Les corps métier sont bornés à 64 Kio ; l'import dispose de la limite fichier configurée plus une marge fixe pour l'enveloppe multipart.

L'ingestion écrit chaque fichier par blocs dans un temporaire situé sur le même volume, calcule son empreinte SHA-256, valide sa taille et sa structure, puis publie un manifeste JSON privé, versionné et remplacé atomiquement. Au démarrage, le backend vérifie le confinement du chemin, la taille, l'empreinte et les métadonnées avant de reparcourir le fichier avec les mêmes limites que lors de l'import. Pour un import retenu, un manifeste absent, tronqué ou incohérent déclenche un repli explicite sur l'échantillon, jamais une sélection par date de modification.

La démo accepte au plus 10 imports et 20 requêtes IA par fenêtre de 10 minutes, dans deux compteurs distincts. Le quota IA est vérifié avant le parsing JSON et partagé entre `/api/ask` et `/api/ai-summary`, y compris en mode fallback ; un dépassement renvoie `429` avec `Retry-After`. Ces compteurs sont globaux, en mémoire et réinitialisés au redémarrage de l'unique processus : ce ne sont ni des quotas par utilisateur ni des quotas OpenAI distribués.

Un verrou partagé autorise un seul import ou calcul analytique lourd à la fois par instance et renvoie `429` avec `Retry-After` lorsqu'elle est occupée. Le cache d'analyses conserve au plus 32 résultats dans un budget estimé de 8 Mio pour les objets retenus, avec des clés composées de l'identifiant immuable du dataset, de l'opération et de ses options. Une réponse qui dépasse seule ce budget est calculée mais n'est pas mémorisée. Le cache réutilise le bundle qualité/anomalies/overview pour l'IA et les rapports, met en cache les agrégations de dashboard dans la limite du budget et élimine les résultats de l'ancien dataset après un import. Ces octets estiment la taille profonde des objets Python mis en cache, pas la mémoire totale du processus. Les métriques concernent uniquement l'instance active ; le cache est vide après un redémarrage.

La plateforme conserve au plus le dernier fichier importé, les 20 rapports les plus récents, 500 événements métier et 1 000 événements de télémétrie IA ; un échec de restauration de ces quotas fait échouer l'écriture au lieu de laisser le stockage croître silencieusement. Les simples consultations `GET` ne remplissent plus l'historique SQLite. Cette persistance est conçue pour l'unique processus backend de démonstration ; plusieurs réplicas nécessiteraient un verrou distribué et un stockage partagé transactionnel.

Pour un CSV, le backend teste uniquement la virgule, le point-virgule et la tabulation, vérifie la cohérence de toutes les lignes, puis transmet le même encodage et le même séparateur à Pandas. Un format ambigu est refusé plutôt qu'interprété silencieusement. Pour un XLSX à plusieurs feuilles, le premier envoi retourne la liste des feuilles de données sans activer ni conserver le fichier ; l'utilisateur choisit ensuite la feuille exacte dans l'interface et confirme l'import. Ce flux prudent transfère donc deux fois un classeur multi-feuilles et consomme deux tentatives du quota d'import.

## Logique d'analyse

Le score Data Quality, borné entre 0 et 100, applique des pénalités déterministes : complétude (50 points), doublons ou identifiants répétés (25), valeurs extrêmes IQR (15), incohérences de type, dates invalides et valeurs infinies (10). Le profilage conserve le type Pandas d'origine et expose aussi un type sémantique, un taux de conversion et le nombre de valeurs invalides. Les libellés métier `NA`, `N/A` et `NULL` sont préservés ; seules les cellules nulles, vides ou composées d'espaces sont traitées comme absentes. Aucune correction n'est appliquée au fichier source.

Les dates ISO, les objets datetime et les années explicites sont normalisés en UTC pour les agrégations. Un format français `JJ/MM/AAAA` est accepté lorsque la convention peut être déduite sans ambiguïté de la colonne ; les formats ambigus ou invalides sont signalés au lieu d'être interprétés silencieusement. Une absence d'agrégat reste `null` dans l'API et s'affiche `—`, jamais comme un faux zéro.

Pour les anomalies, les identifiants et colonnes constantes sont exclus. Les colonnes numériques natives ou textuelles avec au moins 90 % de valeurs convertibles sont retenues ; les valeurs manquantes sont imputées par la médiane et représentées par un indicateur d'absence. Les amplitudes sont bornées avant standardisation afin de supporter les valeurs finies extrêmes, puis `IsolationForest` s'exécute avec une graine fixe. L'API renvoie au plus les 100 observations les mieux classées, tout en conservant le total réel. Le score affiché classe les observations ; il ne représente ni une probabilité ni une causalité.

## Tests et qualité

```powershell
# Depuis la racine
& .\.venv\Scripts\python.exe -m pytest .\backend\tests -q

Set-Location .\frontend
npm run typecheck
npm run lint
npm run build
```

La suite backend utilise des répertoires et une base SQLite temporaires. Elle couvre notamment les dimensions des données, l'audit qualité, les agrégations, les types sémantiques et identifiants, les dates UTC/françaises/ambiguës, la sérialisation JSON stricte des absences, IsolationForest sur nombres textuels et valeurs extrêmes, les séparateurs CSV et champs cités, la sélection de feuille Excel, la restauration CSV/XLSX après redémarrage, l'intégrité et le rollback du manifeste, le streaming CSV/XLSX, les seuils exacts de ressources, les flux sans longueur fiable, la protection des archives Excel, les quotas import/IA, la concurrence, les erreurs de stockage `507`, les caches isolés et bornés, la tarification des tokens cachés, la télémétrie SQLite sans contenu, la rétention, l'authentification précoce du service, le démarrage fail-closed, le fallback IA et les rapports.

### Parcours E2E avec Robot Framework

La suite Robot démarre automatiquement une stack isolée sur les ports `3100` et `8100`, pilote Chrome en mode headless, importe un vrai CSV et parcourt les sept pages. Les éventuels serveurs déjà ouverts sur `3000` et `8000` ne sont pas modifiés.

Les uploads, rapports et événements SQLite du parcours E2E sont écrits dans `tests/robot/results/runtime/`. Le run recrée cet espace avant chaque exécution : il ne modifie donc pas les données locales de démonstration du backend.

Le parcours comporte 17 scénarios : authentification, protection directe du backend, déconnexion, workflow nominal complet, quota IA avec conservation de la question refusée, CSV point-virgule avec champ cité, choix d'une feuille Excel, restauration de ce dataset après un vrai redémarrage FastAPI, XLSX corrompu, atomicité de l'import, détection non applicable, dataset entièrement numérique et indisponibilité de l'API.

```powershell
# Depuis la racine du projet
python -m pip install -r .\tests\robot\requirements.txt
python -m robot --outputdir .\tests\robot\results .\tests\robot\enterprise_data_ia.robot
```

Les preuves d'exécution sont générées dans `tests/robot/results/` : `report.html`, `log.html`, `output.xml`, journaux FastAPI/Next.js et captures automatiques en cas d'échec.

### Intégration continue

Le workflow GitHub Actions [`.github/workflows/ci.yml`](.github/workflows/ci.yml) exécute automatiquement Pytest, le contrôle TypeScript, ESLint, le build Next.js et les 17 scénarios Robot Framework. Les rapports E2E sont conservés comme artefact de CI pendant 14 jours, y compris lorsqu'un scénario échoue.

## Scénario de démonstration en entretien

1. Ouvrir la vue d'ensemble sur l'échantillon Marketing Leads.
2. Importer `backend/data/samples/packaging_data.csv` depuis la topbar.
3. Montrer que le contexte passe réellement à 12 lignes et 10 colonnes sur toutes les vues.
4. Expliquer le score Data Quality puis modifier dimension, mesure et agrégation dans le dashboard.
5. Relancer IsolationForest et examiner les colonnes contributrices d'une anomalie.
6. Poser une question à l'assistant, en montrant le badge fournisseur, le quota global, les tokens mesurés et le coût estimé — ou l'absence explicite d'appel OpenAI en fallback local.
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

Docker Compose rend l'exécution reproductible, mais ne remplace pas une plateforme SaaS multi-tenant : sauvegardes automatisées, stockage objet, quotas distribués et orchestration asynchrone restent à ajouter avant de traiter des données réelles.

Cette version implémente une barrière d'accès et des limites de ressources adaptées à une démonstration publique : mot de passe partagé, cookie HTTP-only signé, jeton privé entre Next.js et FastAPI, corps HTTP et ingestion bornés, quotas locaux import/IA, limite de sortie OpenAI, cache borné, télémétrie de coût et rétention automatique. Elle ne fournit pas encore de comptes individuels, de rôles, d'isolation multi-tenant, de stockage objet cloud ni de file de tâches. Tous les utilisateurs autorisés partagent encore le même dataset actif ; les compteurs de fréquence, le cache et le verrou de calcul restent locaux à l'unique instance de démonstration. Une ouverture multi-réplica ou multi-tenant demanderait des quotas distribués, une comptabilité par utilisateur et un rapprochement avec la facturation officielle du fournisseur.
