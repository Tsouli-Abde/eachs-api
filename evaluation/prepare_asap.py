"""
prepare_asap.py — Prépare le corpus ASAP-SAS pour le batch runner EACHS.

ASAP-SAS (Automated Student Assessment Prize, Short Answer Scoring) :
~17 000 réponses courtes d'étudiants, notées par DEUX correcteurs humains.
C'est la référence humaine réelle qui rend le QWK crédible et comparable
à la littérature (Chang & Ginter mesurent la même chose sur du finnois).

1. Télécharger train.tsv depuis Kaggle :
   https://www.kaggle.com/competitions/asap-sas/data  (train.tsv)
   Colonnes : Id, EssaySet (1-10), Score1, Score2, EssayText

2. Récupérer l'énoncé (prompt) de chaque essay set dans la description
   Kaggle et le coller dans un fichier texte (ex: evaluation/prompts/set1.txt).

3. Générer l'échantillon :
   python evaluation/prepare_asap.py --train train.tsv --essay-set 1 \
       --question-file evaluation/prompts/set1.txt --n 200 \
       --out data/corpus_set1.csv

Sortie : CSV avec item_id, task_type, question, answer, human_score, max_score.
human_score = Score1 (correcteur 1) ; Score2 est conservé pour mesurer
l'accord humain-humain, la borne haute naturelle du QWK IA-humain.
"""

import argparse
import csv
import random
from pathlib import Path

# Barème officiel par essay set (score max attribué par les correcteurs)
MAX_SCORES = {1: 3, 2: 3, 3: 2, 4: 2, 5: 3, 6: 3, 7: 2, 8: 2, 9: 2, 10: 2}

parser = argparse.ArgumentParser()
parser.add_argument("--train", required=True, help="train.tsv d'ASAP-SAS")
parser.add_argument("--essay-set", type=int, required=True, choices=range(1, 11))
parser.add_argument("--question-file", required=True,
                    help="fichier texte contenant l'énoncé de l'essay set")
parser.add_argument("--n", type=int, default=200, help="taille de l'échantillon")
parser.add_argument("--seed", type=int, default=42, help="graine (reproductibilité)")
parser.add_argument("--out", default="data/corpus.csv")
args = parser.parse_args()

question = Path(args.question_file).read_text(encoding="utf-8").strip()
max_score = MAX_SCORES[args.essay_set]

rows = []
with open(args.train, encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f, delimiter="\t")
    for r in reader:
        if int(r["EssaySet"]) != args.essay_set:
            continue
        text = r["EssayText"].strip()
        if len(text) < 10:
            continue
        rows.append({
            "item_id": f"asap{args.essay_set}_{r['Id']}",
            "task_type": "short_answer",
            "question": question,
            "answer": text,
            "human_score": int(r["Score1"]),
            "human_score_2": int(r["Score2"]),
            "max_score": max_score,
        })

print(f"{len(rows)} réponses dans l'essay set {args.essay_set}")

# Échantillonnage stratifié par note humaine : chaque niveau de score est
# représenté proportionnellement, pour un QWK qui a du sens.
random.seed(args.seed)
by_score = {}
for r in rows:
    by_score.setdefault(r["human_score"], []).append(r)
sample = []
for score, group in sorted(by_score.items()):
    k = max(1, round(args.n * len(group) / len(rows)))
    sample.extend(random.sample(group, min(k, len(group))))
random.shuffle(sample)
sample = sample[:args.n]

fields = ["item_id", "task_type", "question", "answer",
          "human_score", "human_score_2", "max_score"]
out_path = Path(args.out)
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(sample)

dist = {}
for r in sample:
    dist[r["human_score"]] = dist.get(r["human_score"], 0) + 1
print(f"{len(sample)} réponses écrites dans {out_path}")
print("Distribution des notes humaines :", dict(sorted(dist.items())))
