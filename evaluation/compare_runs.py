"""
compare_runs.py — Compare deux campagnes sur les mêmes copies.

Sert à isoler l'effet d'une seule variable : présence du barème, changement de
backend, évolution du prompt. La comparaison ne porte que sur les copies
présentes dans les deux fichiers, sinon l'écart mesuré confondrait l'effet
étudié avec une différence d'échantillon.

Usage :
    python evaluation/compare_runs.py \
        --a data/results_set1.jsonl        --label-a "sans bareme" \
        --b data/results_set1_rubric.jsonl --label-b "avec bareme" [--latex]
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# La fonction vient de backend/audit.py et non de metrics.py : ce dernier
# analyse ses arguments au niveau module, si bien que l'importer déclencherait
# son propre CLI.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from audit import quadratic_weighted_kappa  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--a", required=True)
parser.add_argument("--b", required=True)
parser.add_argument("--label-a", default="A")
parser.add_argument("--label-b", default="B")
parser.add_argument("--latex", action="store_true")
args = parser.parse_args()


def charger(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("run_index") != 0 or r.get("ai_score") is None or "error" in r:
                continue
            out[r["item_id"]] = r
    return out


a, b = charger(args.a), charger(args.b)
communs = sorted(set(a) & set(b))
print(f"{args.label_a} : {len(a)} copies exploitables")
print(f"{args.label_b} : {len(b)} copies exploitables")
print(f"copies communes : {len(communs)}\n")
if len(communs) < 2:
    raise SystemExit("Pas assez de copies communes pour comparer.")


def borne(score, maxi):
    return max(0, min(int(maxi), round(float(score))))


def profil(runs):
    y_ia = [borne(runs[i]["ai_score"], runs[i]["max_score"]) for i in communs]
    y_hu = [int(runs[i]["human_score"]) for i in communs]
    n_bins = int(max(runs[i]["max_score"] for i in communs)) + 1
    return {
        "qwk": quadratic_weighted_kappa(y_ia, y_hu, n_bins),
        "exact": sum(x == y for x, y in zip(y_ia, y_hu)) / len(communs),
        "adjacent": sum(abs(x - y) <= 1 for x, y in zip(y_ia, y_hu)) / len(communs),
        "mae": statistics.mean(abs(x - y) for x, y in zip(y_ia, y_hu)),
        "moyenne_ia": statistics.mean(y_ia),
        "distribution": Counter(y_ia),
        "confiance": Counter(runs[i].get("confidence") for i in communs),
    }


pa, pb = profil(a), profil(b)
y_hu = [int(a[i]["human_score"]) for i in communs]

lignes = [
    ("QWK IA / humain", f"{pa['qwk']:.3f}", f"{pb['qwk']:.3f}"),
    ("Accord exact", f"{pa['exact']:.1%}", f"{pb['exact']:.1%}"),
    ("Accord adjacent", f"{pa['adjacent']:.1%}", f"{pb['adjacent']:.1%}"),
    ("Erreur absolue moyenne", f"{pa['mae']:.2f}", f"{pb['mae']:.2f}"),
    ("Note moyenne attribuée", f"{pa['moyenne_ia']:.2f}", f"{pb['moyenne_ia']:.2f}"),
]
largeur = max(len(l[0]) for l in lignes) + 2
print(f"{'':<{largeur}}{args.label_a:>16}{args.label_b:>16}")
for nom, va, vb in lignes:
    print(f"{nom:<{largeur}}{va:>16}{vb:>16}")
print(f"\n{'Note moyenne humaine':<{largeur}}{statistics.mean(y_hu):>16.2f}")

print("\n--- Répartition des notes attribuées ---")
echelle = sorted({*pa["distribution"], *pb["distribution"], *y_hu})
print(f"{'note':<8}" + "".join(f"{n:>8}" for n in echelle))
for label, dist in ((args.label_a, pa["distribution"]),
                    (args.label_b, pb["distribution"]),
                    ("humain", Counter(y_hu))):
    print(f"{label[:7]:<8}" + "".join(f"{dist.get(n, 0):>8}" for n in echelle))
print("\nUne distribution concentrée sur la note maximale signale un correcteur "
      "qui n'exploite pas l'échelle, plutôt qu'un correcteur indulgent.")

print("\n--- Confiance déclarée ---")
for label, conf in ((args.label_a, pa["confiance"]), (args.label_b, pb["confiance"])):
    print(f"  {label:<16}" + "  ".join(f"{k}={v}" for k, v in sorted(conf.items(), key=lambda kv: str(kv[0]))))

if args.latex:
    print("\n=== Lignes LaTeX ===")
    for nom, va, vb in lignes:
        print(f"{nom} & {va} & {vb} \\\\".replace("%", "\\%"))
