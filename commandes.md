# EACHS — Commandes de lancement

## Prérequis
- Docker Desktop lancé (icône baleine active)
- Terminal dans le dossier `eachs-api`
- Ollama installé sur la machine

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

---

### Terminal 2 — API EACHS (FastAPI)
```bash
cd eachs-api
source venv/bin/activate
unset MOODLE_URL && unset MOODLE_TOKEN
uvicorn main:app --reload
```
API accessible sur : **http://localhost:8000**
Dashboard : **http://localhost:8000/dashboard**
Documentation API : **http://localhost:8000/docs**

---

### Terminal 3 — Scheduler (détection automatique des soumissions)
```bash
cd eachs-api
source venv/bin/activate
unset MOODLE_URL && unset MOODLE_TOKEN
python3 scheduler.py
```
Le scheduler vérifie toutes les `CHECK_INTERVAL` secondes (défini dans `.env`).

---

## 2. Paramètres du fichier .env

```
GEMINI_API_KEY=...          # Clé API Gemini (cloud)
MOODLE_URL=http://localhost:8080
MOODLE_TOKEN=...            # Token API Moodle
MOODLE_ADMIN_USER=admin
MOODLE_ADMIN_PASSWORD=Admin1234!
EACHS_URL=http://localhost:8000
AI_BACKEND=local            # local = Mistral | cloud = Gemini
OLLAMA_MODEL=mistral
CHECK_INTERVAL=10           # Secondes entre chaque vérification (10 pour les tests, 60 pour la prod)
```

---

## 3. Changer de modèle IA

### Passer en local (Mistral via Ollama)
```bash
# Dans .env
AI_BACKEND=local
OLLAMA_MODEL=mistral

# Vérifier qu'Ollama tourne
ollama list
ollama run mistral "test"
```

### Passer en cloud (Gemini)
```bash
# Dans .env
AI_BACKEND=cloud
```

---

## 4. Commandes utiles

### Peupler Moodle avec des données de test
```bash
source venv/bin/activate
python3 seed_complete.py
```

### Forcer la réévaluation d'une soumission
```bash
# Supprimer le log correspondant dans audit_log.json
# ou vider tous les logs :
rm audit_log.json
```

### Vérifier les logs d'évaluation
```bash
python3 -c "
import json
with open('audit_log.json') as f:
    logs = json.load(f)
print(f'{len(logs)} évaluations')
for l in logs[-3:]:
    print(f'  [{l[\"task_type\"]}] {l[\"assignment_name\"]} | score={l[\"proposed_score\"]}/{l[\"max_score\"]} | {l[\"human_decision\"] or \"en attente\"}')
"
```

### Réinitialiser complètement (fresh start)
```bash
# Supprimer les logs locaux
rm -f audit_log.json processed_submissions.txt

# Vider Moodle
docker compose exec db mysql -u moodle -pmoodlepass moodle -e "
DELETE FROM mdl_course WHERE id > 1;
DELETE FROM mdl_assign WHERE id > 0;
DELETE FROM mdl_assign_submission WHERE id > 0;
DELETE FROM mdl_assign_grades WHERE id > 0;
"

# Relancer le seed
python3 seed_complete.py
```

---

## 5. Arrêter l'environnement

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

## 6. Accès rapide

| Service | URL |
|---|---|
| Moodle | http://localhost:8080 |
| Dashboard EACHS | http://localhost:8000/dashboard |
| API Docs (Swagger) | http://localhost:8000/docs |
| Logs JSON | http://localhost:8000/logs |
| Stats | http://localhost:8000/stats |
| Kappa | http://localhost:8000/stats/kappa |