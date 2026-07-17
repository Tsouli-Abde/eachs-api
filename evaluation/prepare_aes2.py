"""
prepare_aes2.py — Prépare le corpus "Learning Agency Lab - Automated Essay
Scoring 2.0" (ASAP 2.0) pour le batch runner EACHS.

~24 000 dissertations argumentatives, notées holistiquement sur une échelle
1-6 par deux groupes de correcteurs indépendants, avec un score final arbitré.
Contrairement à ASAP-SAS, le CSV public ne contient que ce score final (pas les
deux notes brutes) : pas de borne haute humain-humain calculable avec ce
dataset — metrics.py ignorera simplement cette section (human_score_2 absent).

Autre différence avec ASAP-SAS : le CSV ne fournit ni la consigne précise ni
le(s) texte(s) source de chaque essai, seulement le texte de l'essai et sa
note. On note donc chaque essai avec la grille holistique générique
(evaluation/prompts/aes2_holistic_rubric.txt), exactement comme le fait la
compétition Kaggle elle-même (le texte de l'essai seul, sans la consigne
d'origine).

1. Télécharger train.csv depuis Kaggle :
   https://www.kaggle.com/competitions/learning-agency-lab-automated-essay-scoring-2/data
   Colonnes : essay_id, full_text, score (1-6)

2. Générer l'échantillon :
   python evaluation/prepare_aes2.py --train train.csv --n 200 \
       --out data/corpus_aes2.csv

Sortie : CSV avec item_id, task_type, question, answer, human_score, max_score.
"""

import argparse
import csv
import random
from pathlib import Path

MAX_SCORE = 6

parser = argparse.ArgumentParser()
parser.add_argument("--train", required=True, help="train.csv d'AES 2.0")
parser.add_argument("--question-file",
                    default="evaluation/prompts/aes2_holistic_rubric.txt",
                    help="fichier texte contenant la consigne + grille (identique pour tous les essais)")
parser.add_argument("--n", type=int, default=200, help="taille de l'échantillon")
parser.add_argument("--seed", type=int, default=42, help="graine (reproductibilité)")
parser.add_argument("--out", default="data/corpus_aes2.csv")
args = parser.parse_args()

question = Path(args.question_file).read_text(encoding="utf-8").strip()

rows = []
with open(args.train, encoding="utf-8", errors="replace") as f:
    reader = csv.DictReader(f)
    for r in reader:
        text = r["full_text"].strip()
        if len(text) < 10:
            continue
        rows.append({
            "item_id": f"aes2_{r['essay_id']}",
            "task_type": "essay",
            "question": question,
            "answer": text,
            "human_score": int(r["score"]),
            "max_score": MAX_SCORE,
        })

print(f"{len(rows)} essais dans train.csv")

# Échantillonnage stratifié par note humaine (comme prepare_asap.py).
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

fields = ["item_id", "task_type", "question", "answer", "human_score", "max_score"]
out_path = Path(args.out)
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(sample)

dist = {}
for r in sample:
    dist[r["human_score"]] = dist.get(r["human_score"], 0) + 1
print(f"{len(sample)} essais écrits dans {out_path}")
print("Distribution des notes humaines :", dict(sorted(dist.items())))
