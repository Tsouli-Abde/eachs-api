"""
batch_runner.py — Fait évaluer un corpus en masse par l'API EACHS.

Appelle POST /evaluate pour chaque ligne du CSV produit par prepare_asap.py
(ou tout CSV avec les colonnes item_id, task_type, question, answer,
human_score, max_score).

Robustesse intégrée (file d'attente + reprise) :
- résultats écrits au fil de l'eau dans un JSONL ; en cas d'interruption,
  relancer la même commande reprend là où ça s'est arrêté
- retry avec backoff exponentiel sur timeout / 429 / 5xx
- régulation du débit (--delay) pour respecter les rate limits

Concurrence : --concurrency N traite N copies en parallèle (défaut 1 = séquentiel,
comportement d'origine). Avec --concurrency > 1, --delay n'est plus utilisé comme
pause entre appels (le nombre de workers régule déjà le débit) ; il sert uniquement
de base au backoff exponentiel en cas de retry.

Mesure de stabilité : --repeats N évalue chaque copie N fois
(run_index 0..N-1), ce qui permet de mesurer la cohérence inter-passages.

Usage typique :
    python evaluation/batch_runner.py --corpus data/corpus_set1.csv \
        --api http://localhost:8000 --out data/results_set1.jsonl \
        --delay 3 --repeats 1
    # avec concurrence (backend qui supporte la charge) :
    python evaluation/batch_runner.py --corpus data/corpus_set1.csv \
        --api http://localhost:8000 --out data/results_set1.jsonl \
        --concurrency 4
    # puis, stabilité sur un sous-échantillon :
    python evaluation/batch_runner.py --corpus data/corpus_set1.csv \
        --api http://localhost:8000 --out data/results_stability.jsonl \
        --delay 3 --repeats 5 --limit 30
"""

import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

parser = argparse.ArgumentParser()
parser.add_argument("--corpus", required=True)
parser.add_argument("--api", default="http://localhost:8000")
parser.add_argument("--out", default="data/results.jsonl")
parser.add_argument("--delay", type=float, default=3.0,
                    help="secondes entre deux appels en mode séquentiel ; "
                         "base du backoff exponentiel sur retry dans tous les cas")
parser.add_argument("--repeats", type=int, default=1,
                    help="nombre d'évaluations par copie (stabilité)")
parser.add_argument("--limit", type=int, default=0,
                    help="ne traiter que les N premières copies (0 = toutes)")
parser.add_argument("--max-retries", type=int, default=4)
parser.add_argument("--timeout", type=int, default=120)
parser.add_argument("--concurrency", type=int, default=1,
                    help="nombre de requêtes en parallèle (défaut 1 = séquentiel)")
args = parser.parse_args()

# --- corpus ---
with open(args.corpus, encoding="utf-8") as f:
    items = list(csv.DictReader(f))
if args.limit:
    items = items[: args.limit]

# --- reprise : clés (item_id, run_index) déjà traitées ---
out_path = Path(args.out)
out_path.parent.mkdir(parents=True, exist_ok=True)
done = set()
if out_path.exists():
    with open(out_path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                done.add((r["item_id"], r["run_index"]))
            except (json.JSONDecodeError, KeyError):
                continue


def evaluate(item, run_index):
    payload = {
        "student_id": f"batch_{item['item_id']}",
        "assignment_id": f"batch_run{run_index}",
        "task_type": item["task_type"],
        "question": item["question"],
        "student_answer": item["answer"],
        "max_score": float(item["max_score"]),
    }
    delay = args.delay
    for attempt in range(args.max_retries + 1):
        try:
            resp = requests.post(f"{args.api}/evaluate", json=payload,
                                 timeout=args.timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.RequestException(f"HTTP {resp.status_code}")
            # 4xx autre que 429 : erreur définitive, inutile de réessayer
            return {"error": f"HTTP {resp.status_code}", "detail": resp.text[:300]}
        except requests.RequestException as e:
            if attempt == args.max_retries:
                return {"error": str(e)}
            wait = delay * (2 ** attempt)
            print(f"    retry {attempt + 1}/{args.max_retries} dans {wait:.0f}s ({e})")
            time.sleep(wait)


tasks = [(item, run) for item in items for run in range(args.repeats)
         if (item["item_id"], run) not in done]
total = len(items) * args.repeats
count_done = len(done)
lock = threading.Lock()
out_file = open(out_path, "a", encoding="utf-8")

print(f"{len(items)} copies x {args.repeats} passages ; {len(done)} déjà faits ; "
      f"{len(tasks)} restants (concurrence={args.concurrency})")


def to_float(value):
    """
    Note de référence optionnelle : un corpus de robustesse n'en comporte pas
    forcément, ses copies n'ayant pas été notées par un correcteur humain.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def process(task):
    global count_done
    item, run = task
    result = evaluate(item, run)
    record = {
        "item_id": item["item_id"],
        "run_index": run,
        "task_type": item["task_type"],
        "human_score": to_float(item.get("human_score")),
        "human_score_2": to_float(item.get("human_score_2")),
        "max_score": float(item["max_score"]),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if result and "error" not in result:
        record.update({
            "ai_score": result.get("score", result.get("proposed_score")),
            "confidence": result.get("confidence"),
            "feedback": result.get("feedback"),
            "manipulation_detected": result.get("manipulation_detected", False),
            # Sans ce champ, impossible de distinguer une évaluation erronée
            # rattrapée par la révision humaine d'une évaluation erronée partie
            # en décision automatique — la différence qui fait toute la
            # gouvernance.
            "requires_human_review": result.get("requires_human_review"),
            "backend": result.get("backend"),
            "prompt_version": result.get("prompt_version"),
        })
    else:
        record["error"] = (result or {}).get("error", "réponse vide")

    with lock:
        out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        out_file.flush()
        count_done += 1
        n = count_done
    score = record.get("ai_score", "ERR")
    print(f"[{n}/{total}] {item['item_id']} run{run} "
          f"-> IA {score} / humain {item['human_score']}")
    if args.concurrency <= 1:
        time.sleep(args.delay)


if args.concurrency <= 1:
    for task in tasks:
        process(task)
else:
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(process, t): t for t in tasks}
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                # Une copie qui échoue ne doit pas emporter la campagne
                # entière : les autres continuent, et la reprise traitera
                # celle-ci au prochain lancement.
                item, run = futures[f]
                print(f"    ECHEC {item['item_id']} run{run} : "
                      f"{type(e).__name__}: {e}")

out_file.close()
print(f"Terminé. Résultats dans {out_path}")
