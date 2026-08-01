# EACHS — Évaluation Assistée sous Contrôle Humain Structuré

API d'évaluation pédagogique assistée par IA, intégrée à Moodle, avec contrôle
humain systématique (HITL) et journal d'audit conforme à l'AI Act.

## Arborescence

```
eachs-api/
├── backend/            Code applicatif (API FastAPI, IA, Moodle, audit)
│   ├── main.py           API REST + endpoints /evaluate, /review, /stats, /dashboard
│   ├── models.py         Schémas Pydantic
│   ├── evaluator.py      Backends IA (Ollama local, Gemini, OpenRouter, interne)
│   ├── extractor.py      Extraction de texte (PDF, DOCX, images…)
│   ├── audit.py          Journal d'audit sur SQLite (thread-safe)
│   └── scheduler.py      Détection auto des soumissions Moodle
├── dashboard/          Interface web (HTML + JS) servie par l'API
├── evaluation/         Outils de mesure (concordance, robustesse, protocole)
│   ├── prepare_asap.py       Prépare un corpus depuis ASAP-SAS
│   ├── prepare_aes2.py       Prépare un corpus depuis AES 2.0
│   ├── batch_runner.py       Évalue un corpus en masse via l'API
│   ├── metrics.py            Calcule QWK, accord exact/adjacent, stabilité
│   ├── build_adversarial.py  Construit le corpus de soumissions adverses
│   ├── redteam_metrics.py    Taux de détection et faux positifs
│   ├── protocol_report.py    Analyse la campagne Moodle (routage, profils)
│   ├── run_campaign.sh       Rejoue une campagne complète pour un backend
│   └── prompts/              Énoncés des essay sets ASAP-SAS
├── scripts/            Utilitaires (seed Moodle, migration, maintenance)
├── samples/            Exemples de réponses pour tests manuels
├── data/               Données runtime (base d'audit, corpus, résultats) — ignoré par git
├── docs/               commandes.md et documentation
├── docker-compose.yml  Moodle + base de données
├── Dockerfile
└── requirements.txt
```

## Démarrage rapide

Voir **[docs/commandes.md](docs/commandes.md)** pour le détail. En résumé, 3 terminaux :

```bash
# 1. Moodle + base
docker compose up

# 2. API EACHS (backend IA local par défaut : Mistral via Ollama)
source venv/bin/activate
uvicorn main:app --app-dir backend --reload

# 3. Scheduler (détection des soumissions)
python3 backend/scheduler.py
```

Dashboard : http://localhost:8000/dashboard · Swagger : http://localhost:8000/docs

## Journal d'audit (SQLite)

Le journal d'évaluation est stocké dans `data/audit_log.sqlite` :
- **thread-safe** : l'API et le scheduler peuvent écrire en parallèle sans
  corrompre le fichier (limite de l'ancien `audit_log.json`) ;
- **reviewer_id** : chaque décision humaine enregistre l'identifiant du
  réviseur, ce qui complète le graphe PROV (l'agent enseignant devient
  identifiable).

Migrer un ancien journal JSON (idempotent) :
```bash
python3 scripts/migrate_json_to_sqlite.py audit_log.json
```

## Évaluation en masse (concordance QWK)

Obtenir des mesures de concordance crédibles (QWK sur des centaines de copies
avec une vraie référence humaine, comparable à la littérature).

### Étape 1 — Récupérer le corpus ASAP-SAS
1. https://www.kaggle.com/competitions/asap-sas/data → `train.tsv`
   (~17 000 réponses courtes, notées par DEUX correcteurs humains)
2. Copier l'énoncé de l'essay set choisi (description Kaggle) dans un fichier
   texte, ex. `evaluation/prompts/set1.txt`
3. Échantillonner (stratifié par note) :
```bash
python3 evaluation/prepare_asap.py --train train.tsv --essay-set 1 \
    --question-file evaluation/prompts/set1.txt --n 200 --out data/corpus_set1.csv
```
Conseil : 2 essay sets différents × 200 réponses = 400 points de mesure.

### Étape 2 — Lancer le batch (l'API EACHS doit tourner)
```bash
# run principal (1 passage par copie)
python3 evaluation/batch_runner.py --corpus data/corpus_set1.csv \
    --api http://localhost:8000 --out data/results_set1.jsonl --delay 3

# stabilité : 5 passages sur 30 copies
python3 evaluation/batch_runner.py --corpus data/corpus_set1.csv \
    --api http://localhost:8000 --out data/results_stability.jsonl \
    --repeats 5 --limit 30 --delay 3
```
Interruptible et reprenable : relancer la même commande reprend où ça s'est
arrêté. Retry automatique sur timeout/429/5xx. Avec Gemini gratuit (5 req/min),
mettre `--delay 13`.

### Étape 3 — Calculer les métriques
```bash
python3 evaluation/metrics.py data/results_set1.jsonl --latex
```
Sort le QWK IA/humain, le QWK humain/humain (borne haute naturelle), l'accord
exact/adjacent, la ventilation par confiance déclarée, la stabilité
inter-passages, et les lignes LaTeX pour le mémoire.

## Campagne complète pour un backend

`run_campaign.sh` rejoue concordance et robustesse à gouvernance constante,
dans une base d'audit isolée par backend (une campagne de masse ne doit pas
écraser celle que lit le tableau de bord) :

```bash
./evaluation/run_campaign.sh local    mistral
./evaluation/run_campaign.sh cloud    gemini-2.5-flash
./evaluation/run_campaign.sh internal <modele>   # poste entreprise (VPN)
```

## Robustesse : soumissions adverses

Le taux de détection se mesure, il ne se postule pas. Le corpus couvre six
familles d'attaques et inclut des **contrôles légitimes** (copies honnêtes
traitant de l'injection de prompt), sans lesquels on ne mesurerait jamais les
faux positifs :

```bash
python3 evaluation/build_adversarial.py --out data/corpus_adversarial.csv
python3 evaluation/batch_runner.py --corpus data/corpus_adversarial.csv \
    --api http://localhost:8000 --out data/results_adversarial.jsonl
python3 evaluation/redteam_metrics.py --corpus data/corpus_adversarial.csv \
    --results data/results_adversarial.jsonl --latex
```

## Campagne Moodle (protocole 4 types × 4 profils)

```bash
# .env : SEED_COURSE_SUFFIX, EACHS_COURSES, AUDIT_DB_PATH
python3 scripts/seed_demo.py          # 4 cours, 16 devoirs, 4 profils, 64 copies
python3 backend/scheduler.py          # évalue le périmètre déclaré
AUDIT_DB_PATH=data/audit_moodle.sqlite python3 evaluation/protocol_report.py
```

`EACHS_COURSES` limite le scheduler aux cours où l'assistance a été activée :
un établissement ne déploie pas un correcteur IA sur toute sa plateforme d'un
coup, la décision se prend cours par cours.

## Backends IA

Configurable via `AI_BACKEND` dans `.env` : `local` (Mistral via Ollama, défaut),
`cloud` (Gemini), `openrouter`, `internal`. Voir `docs/commandes.md § 3`.

## Pistes suivantes (non codées)

1. Validation du barème par l'enseignant avant usage.
2. Webhook Moodle (plugin PHP) pour remplacer le polling du scheduler.
3. Seuils de confiance configurables par type de tâche dans le dashboard.
4. Chaînage d'empreintes SHA-256 des enregistrements (immuabilité vérifiable).
5. Red teaming du SYSTEM_GUARD (30-50 soumissions adverses, colonne
   `manipulation_detected` déjà présente dans les résultats).
