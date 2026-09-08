# Checklist de release

Cette checklist évite qu'une version soit déployée avant la fin des contrôles automatisés. Elle ne contient aucun secret et peut être utilisée pour chaque release.

## 1. Préparer la branche

- partir d'une branche créée depuis `main` à jour ;
- vérifier que seuls les fichiers attendus sont suivis par Git ;
- ouvrir une pull request au lieu de pousser directement sur `main`.

## 2. Valider localement

```powershell
python -m pip install -r .\backend\requirements-dev.txt
python -m pip install -r .\backend\requirements-tools.txt
python .\backend\scripts\lock_dependencies.py --check
python -m pytest .\backend\tests -q
python -m pip install pip-audit==2.10.1
python -m pip_audit --strict --progress-spinner=off --requirement .\backend\requirements.txt
python -m pip_audit --strict --progress-spinner=off --requirement .\backend\requirements-dev.txt
python -m pip_audit --strict --progress-spinner=off --requirement .\backend\requirements-tools.txt

Set-Location .\frontend
npm ci
npm audit --omit=dev --audit-level=high
npm run typecheck
npm run lint
npm run build
Set-Location ..

docker compose config --quiet
docker compose build
```

Le parcours Robot Framework complet reste exécuté par GitHub Actions. Il peut aussi être lancé localement avec les commandes documentées dans le README.

## 3. Fusionner avec les contrôles requis

La branche `main` doit exiger la réussite des contrôles suivants avant fusion :

- `Backend · Pytest`, qui inclut l'audit du verrou Python runtime ;
- `Frontend · TypeScript, ESLint, build`, qui inclut l'audit npm de production ;
- `Containers · Docker Compose smoke` ;
- `E2E · Robot Framework`.

Une fusion ne doit être effectuée que lorsque la pull request est à jour et que tous ces contrôles sont verts.

## 4. Bloquer Railway jusqu'à la fin de la CI

Dans **Settings > Source** de chacun des deux services Railway, activer **Wait for CI**. Railway doit alors placer le déploiement en attente pendant GitHub Actions et l'ignorer si un workflow échoue.

Pour le backend, vérifier également :

- un volume attaché avec le chemin de montage `/var/lib/copilot` ;
- `COPILOT_UPLOADS_DIR=/var/lib/copilot/uploads` ;
- `COPILOT_REPORTS_DIR=/var/lib/copilot/reports` ;
- `COPILOT_DATABASE_PATH=/var/lib/copilot/history.db` ;
- une seule réplique tant que SQLite, le cache et les quotas restent locaux au processus.

Ne jamais placer `BACKEND_SERVICE_TOKEN`, `SESSION_SECRET`, `DEMO_ACCESS_PASSWORD` ou `OPENAI_API_KEY` dans Git.

## 5. Contrôler la production

Après le déploiement :

1. vérifier que `GET /api/health` répond `200` ;
2. vérifier que `/login` répond `200` ;
3. vérifier qu'une route métier FastAPI publique sans jeton répond `401` ;
4. ouvrir une session et exécuter un parcours court : import, dashboard, anomalies et rapport ;
5. confirmer dans Railway que les deux services utilisent le même commit Git.

En cas d'échec, conserver les journaux et utiliser le rollback Railway vers le dernier déploiement validé.

## 6. Préparer une démonstration d'entretien

- ouvrir une session neuve ;
- importer explicitement `backend/data/samples/marketing_leads.csv` afin de rendre le point de départ déterministe ;
- garder `backend/data/samples/packaging_data.csv` prêt pour démontrer un nouvel import ;
- n'utiliser que les données synthétiques fournies ;
- vérifier le fallback local avant la démonstration si aucune clé OpenAI n'est configurée.
