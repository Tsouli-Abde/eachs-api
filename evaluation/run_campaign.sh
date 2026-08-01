#!/usr/bin/env bash
# run_campaign.sh — Rejoue une campagne de mesure complète pour un backend donné.
#
# Objectif : que la comparaison entre familles de modèles se fasse à gouvernance
# strictement constante. Seul le backend d'inférence change ; prompt, routage,
# corpus et métriques sont identiques d'une exécution à l'autre.
#
# Chaque backend écrit dans SA PROPRE base d'audit. Sans cette isolation, une
# campagne de masse écrase la base que lit le tableau de bord — c'est ce qui a
# fait perdre les données d'une campagne précédente.
#
#   ./evaluation/run_campaign.sh local     mistral
#   ./evaluation/run_campaign.sh local     qwen2.5:3b
#   ./evaluation/run_campaign.sh cloud     gemini-2.5-flash
#   ./evaluation/run_campaign.sh internal  <modele>     # depuis le poste entreprise (VPN)
#
# Prérequis : venv activable, Ollama lancé pour le backend local, clés d'API
# renseignées dans .env pour cloud/internal, et train.tsv d'ASAP-SAS à la racine.

set -euo pipefail

BACKEND="${1:-local}"
MODELE="${2:-mistral}"
N="${3:-100}"          # nombre de copies ASAP échantillonnées
PORT="${PORT:-8000}"

# Concurrence : seul le backend interne d'entreprise a supporté les appels
# parallèles. Ollama et l'API Gemini gratuite échouent au-delà d'un appel à la
# fois — d'où un débit régulé par --delay pour ces deux-là.
case "$BACKEND" in
  internal) CONCURRENCY=4 ; DELAY=0  ;;
  cloud)    CONCURRENCY=1 ; DELAY=13 ;;   # quota gratuit ~5 requêtes/minute
  *)        CONCURRENCY=1 ; DELAY=1  ;;
esac

SLUG="$(echo "${BACKEND}_${MODELE}" | tr -c 'A-Za-z0-9_.-' '_')"
DB="data/audit_${SLUG}.sqlite"
CORPUS_ASAP="data/corpus_set1.csv"
CORPUS_ADV="data/corpus_adversarial.csv"
RES_ASAP="data/results_${SLUG}.jsonl"
RES_ADV="data/results_adv_${SLUG}.jsonl"

echo "=============================================================="
echo " Campagne EACHS — backend=$BACKEND modele=$MODELE"
echo " base d'audit isolée : $DB"
echo " concurrence=$CONCURRENCY delay=${DELAY}s"
echo "=============================================================="

# --- corpus (regénérés seulement s'ils manquent : l'échantillon doit rester
# --- le même d'un backend à l'autre, sinon la comparaison ne vaut rien)
if [ ! -f "$CORPUS_ASAP" ]; then
  echo "[1/5] Échantillonnage ASAP-SAS (graine fixe)..."
  python evaluation/prepare_asap.py --train train.tsv --essay-set 1 \
      --question-file evaluation/prompts/set1.txt --n "$N" --out "$CORPUS_ASAP"
else
  echo "[1/5] Corpus ASAP déjà présent, réutilisé tel quel."
fi

if [ ! -f "$CORPUS_ADV" ]; then
  echo "[2/5] Construction du corpus adverse..."
  python evaluation/build_adversarial.py --out "$CORPUS_ADV"
else
  echo "[2/5] Corpus adverse déjà présent, réutilisé tel quel."
fi

# --- API dédiée à cette campagne
echo "[3/5] Démarrage de l'API (backend=$BACKEND)..."
pkill -f "uvicorn main:app.*--port $PORT" 2>/dev/null || true
sleep 1
AI_BACKEND="$BACKEND" OLLAMA_MODEL="$MODELE" AUDIT_DB_PATH="$DB" \
  nohup uvicorn main:app --app-dir backend --port "$PORT" \
  > "/tmp/eachs_api_${SLUG}.log" 2>&1 &
sleep 6
curl -sf "http://localhost:$PORT/" > /dev/null || {
  echo "L'API n'a pas démarré, voir /tmp/eachs_api_${SLUG}.log" >&2; exit 1; }
echo "      API prête sur le port $PORT."

# --- mesures
echo "[4/5] Concordance sur corpus ASAP-SAS ($N copies)..."
python evaluation/batch_runner.py --corpus "$CORPUS_ASAP" \
    --api "http://localhost:$PORT" --out "$RES_ASAP" \
    --delay "$DELAY" --concurrency "$CONCURRENCY"

echo "[5/5] Robustesse sur corpus adverse..."
python evaluation/batch_runner.py --corpus "$CORPUS_ADV" \
    --api "http://localhost:$PORT" --out "$RES_ADV" \
    --delay "$DELAY" --concurrency "$CONCURRENCY"

echo
echo "================= CONCORDANCE ($BACKEND/$MODELE) ================="
python evaluation/metrics.py "$RES_ASAP" --latex

echo
echo "================= ROBUSTESSE ($BACKEND/$MODELE) ================="
python evaluation/redteam_metrics.py --corpus "$CORPUS_ADV" \
    --results "$RES_ADV" --latex

echo
echo "Résultats : $RES_ASAP · $RES_ADV · base d'audit $DB"
