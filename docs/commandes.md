# EACHS — Commandes de lancement

## Prérequis
- Docker Desktop lancé (icône baleine active)
- Terminal dans le dossier `eachs-api`
- Ollama installé sur la machine (backend IA local par défaut)

> Nouvelle arborescence : le code applicatif est dans `backend/`, le dashboard
> dans `dashboard/`, les outils de mesure dans `evaluation/`, les scripts
> utilitaires dans `scripts/`, et les données runtime (base d'audit, corpus,
> résultats) dans `data/`.

---

## 1. Lancer l'environnement complet

Ouvrir **3 terminaux** dans `eachs-api`.

### Terminal 1 — Docker (Moodle + Base de données)
```bash
cd eachs-api
docker compose up
```
Attendre : `Apache/2.4.54 configured -- resuming normal operations`
Moodle accessible sur : **http://localhost:8080**
Login : `admin` / `Admin1234!`

> **Si le port 8080 est déjà pris** (autre projet en cours), définir `MOODLE_PORT`
> dans `.env` — le `docker-compose.yml` le lit, avec 8080 pour défaut :
> ```
> MOODLE_PORT=8085
> MOODLE_URL=http://localhost:8085
> ```
> L'image utilisée lit `$CFG->wwwroot` depuis `getenv('MOODLE_URL')` : le
> changement de port est donc pris en compte au redémarrage du conteneur, sans
> retoucher `config.php`, même sur une instance déjà installée. Vérifier après
> démarrage que `siteurl` correspond bien :
> ```bash
> curl -s "http://localhost:8085/webservice/rest/server.php?wstoken=$MOODLE_TOKEN&wsfunction=core_webservice_get_site_info&moodlewsrestformat=json"
> ```

> ⚠️ `docker compose up` ne démarre **que** Moodle + la base. L'API EACHS tourne
> en **local** (Terminal 2), pas dans Docker, car le backend IA local (Ollama)
> tourne sur ta machine : un conteneur ne le verrait pas. Ne lance donc pas
> l'API en conteneur en même temps (elle occuperait le port 8000 et échouerait
> avec « Failed to connect to Ollama »). Si tu veux quand même la version
> conteneur : `docker compose --profile api up`.

---

### Terminal 2 — API EACHS (FastAPI)
```bash
cd eachs-api
source venv/bin/activate
unset MOODLE_URL && unset MOODLE_TOKEN
uvicorn main:app --app-dir backend --reload
```
`--app-dir backend` indique à uvicorn où se trouve le code applicatif.
API accessible sur : **http://localhost:8000**
Dashboard : **http://localhost:8000/dashboard**
Documentation API : **http://localhost:8000/docs**

---

### Terminal 3 — Scheduler (détection automatique des soumissions)
```bash
cd eachs-api
source venv/bin/activate
unset MOODLE_URL && unset MOODLE_TOKEN
python3 backend/scheduler.py
```
Le scheduler vérifie toutes les `CHECK_INTERVAL` secondes (défini dans `.env`).

---

## 2. Paramètres du fichier .env

```
GEMINI_API_KEY=...          # Clé API Gemini (cloud, optionnel)
MOODLE_URL=http://localhost:8080
MOODLE_TOKEN=...            # Token API Moodle
MOODLE_ADMIN_USER=admin
MOODLE_ADMIN_PASSWORD=Admin1234!
EACHS_URL=http://localhost:8000
AI_BACKEND=local            # local = Mistral via Ollama (défaut)
OLLAMA_MODEL=mistral
CHECK_INTERVAL=10           # Secondes entre chaque vérification (10 tests, 60 prod)
```

---

## 3. Changer de modèle IA

### Backend local (Mistral via Ollama) — configuration par défaut
```bash
# Dans .env
AI_BACKEND=local
OLLAMA_MODEL=mistral

# Vérifier qu'Ollama tourne
ollama list
ollama run mistral "test"
```

### Autres backends (optionnels)
```bash
# Dans .env, au choix :
AI_BACKEND=cloud       # Gemini
AI_BACKEND=openrouter  # OpenRouter
AI_BACKEND=internal    # API interne entreprise
```

---

## 4. Commandes utiles

### Peupler Moodle avec des données de test
```bash
source venv/bin/activate
python3 scripts/seed_complete.py
```

### Journal d'audit : SQLite au lieu de JSON
Le journal est désormais une base SQLite : `data/audit_log.sqlite`
(thread-safe, pas de corruption quand l'API et le scheduler écrivent en même temps).

Migrer un ancien `audit_log.json` vers la base (idempotent) :
```bash
python3 scripts/migrate_json_to_sqlite.py audit_log.json
```

Vérifier les logs d'évaluation :
```bash
python3 -c "
import sys; sys.path.insert(0, 'backend')
from audit import get_all_logs
logs = get_all_logs()
print(f'{len(logs)} évaluations')
for l in logs[-3:]:
    print(f'  [{l[\"task_type\"]}] {l[\"assignment_name\"]} | score={l[\"proposed_score\"]}/{l[\"max_score\"]} | {l[\"human_decision\"] or \"en attente\"}')
"
```

### Forcer la réévaluation d'une soumission
```bash
# Vider tout le journal (repart de zéro) :
rm -f data/audit_log.sqlite
```

### Réinitialiser complètement (fresh start)
```bash
# Supprimer les données locales
rm -f data/audit_log.sqlite processed_submissions.txt

# Vider Moodle
docker compose exec db mysql -u moodle -pmoodlepass moodle -e "
DELETE FROM mdl_course WHERE id > 1;
DELETE FROM mdl_assign WHERE id > 0;
DELETE FROM mdl_assign_submission WHERE id > 0;
DELETE FROM mdl_assign_grades WHERE id > 0;
"

# Relancer le seed
python3 scripts/seed_complete.py
```

---

## 5. Mesurer la concordance (QWK) — outils du dossier evaluation/

Voir `README.md` (section « Évaluation en masse ») pour le détail. En bref :
```bash
# 1. Préparer un corpus depuis ASAP-SAS
python3 evaluation/prepare_asap.py --train train.tsv --essay-set 1 \
    --question-file evaluation/prompts/set1.txt --n 200 --out data/corpus_set1.csv

# 2. Lancer le batch (l'API EACHS doit tourner)
python3 evaluation/batch_runner.py --corpus data/corpus_set1.csv \
    --api http://localhost:8000 --out data/results_set1.jsonl --delay 3

# 3. Calculer les métriques
python3 evaluation/metrics.py data/results_set1.jsonl --latex
```

---

## 6. Arrêter l'environnement

```bash
# Terminal scheduler : Ctrl+C
# Terminal uvicorn  : Ctrl+C
# Terminal Docker   : Ctrl+C puis docker compose down
```

Pour arrêter Docker et supprimer les volumes (reset complet) :
```bash
docker compose down -v
```

---

## 7. Accès rapide

| Service | URL |
|---|---|
| Moodle | http://localhost:8080 |
| Dashboard EACHS | http://localhost:8000/dashboard |
| API Docs (Swagger) | http://localhost:8000/docs |
| Logs (JSON via API) | http://localhost:8000/logs |
| Stats | http://localhost:8000/stats |
| Kappa | http://localhost:8000/stats/kappa |
