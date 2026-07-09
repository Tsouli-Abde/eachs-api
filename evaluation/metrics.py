"""
metrics.py — Calcule les métriques du chapitre 6 à partir des résultats batch.

Entrée : le JSONL produit par batch_runner.py.
Sorties :
- QWK IA vs correcteur humain 1 (la métrique de référence)
- QWK correcteur 1 vs correcteur 2 (accord humain-humain = borne haute,
  disponible si le corpus contient human_score_2)
- accord exact et adjacent, erreur absolue moyenne
- ventilation par niveau de confiance déclaré par le modèle
- stabilité inter-passages si --repeats > 1 a été utilisé (écart-type
  par copie + QWK entre passages)
- lignes LaTeX prêtes pour le tableau du mémoire (--latex)

Usage :
    python evaluation/metrics.py data/results_set1.jsonl
    python evaluation/metrics.py data/results_set1.jsonl --latex
"""

import argparse
import json
import statistics
import sys


def quadratic_weighted_kappa(y_ai, y_human, n_bins=None):
    """QWK entre deux listes de notes discrétisées (entiers)."""
    if not y_ai or len(y_ai) != len(y_human):
        return None
    lo = min(min(y_ai), min(y_human))
    hi = max(max(y_ai), max(y_human))
    if n_bins is None:
        n_bins = hi - lo + 1
    if n_bins < 2:
        return None
    n = len(y_ai)
    obs = [[0] * n_bins for _ in range(n_bins)]
    for a, h in zip(y_ai, y_human):
        obs[a - lo][h - lo] += 1
    hist_a = [sum(obs[i][j] for j in range(n_bins)) for i in range(n_bins)]
    hist_h = [sum(obs[i][j] for i in range(n_bins)) for j in range(n_bins)]
    num = den = 0.0
    for i in range(n_bins):
        for j in range(n_bins):
            w = ((i - j) ** 2) / ((n_bins - 1) ** 2)
            expected = hist_a[i] * hist_h[j] / n
            num += w * obs[i][j]
            den += w * expected
    if den == 0:
        return None
    return 1.0 - num / den


parser = argparse.ArgumentParser()
parser.add_argument("results")
parser.add_argument("--latex", action="store_true")
args = parser.parse_args()

records = []
with open(args.results, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

ok = [r for r in records if "error" not in r and r.get("ai_score") is not None]
errors = len(records) - len(ok)
print(f"{len(records)} enregistrements, {len(ok)} exploitables, {errors} erreurs\n")
if not ok:
    sys.exit("Aucun résultat exploitable.")


def to_int_scale(score, max_score):
    """Ramène un score IA (échelle continue) sur l'échelle entière humaine."""
    return max(0, min(int(max_score), round(float(score))))


# ---- passage principal : run_index == 0 ----
main_run = [r for r in ok if r["run_index"] == 0]
y_ai = [to_int_scale(r["ai_score"], r["max_score"]) for r in main_run]
y_h1 = [int(r["human_score"]) for r in main_run]
n_bins = int(max(r["max_score"] for r in main_run)) + 1

qwk = quadratic_weighted_kappa(y_ai, y_h1, n_bins)
exact = sum(a == h for a, h in zip(y_ai, y_h1)) / len(y_ai)
adjacent = sum(abs(a - h) <= 1 for a, h in zip(y_ai, y_h1)) / len(y_ai)
mae = sum(abs(a - h) for a, h in zip(y_ai, y_h1)) / len(y_ai)


def interpret(k):
    if k is None: return "N/A"
    if k < 0.4: return "faible"
    if k < 0.6: return "modéré"
    if k < 0.8: return "substantiel"
    return "quasi parfait"


print("=== Concordance IA / correcteur humain 1 ===")
print(f"  n = {len(main_run)}")
print(f"  QWK              : {qwk:.3f}  (accord {interpret(qwk)})")
print(f"  Accord exact     : {exact:.1%}")
print(f"  Accord adjacent  : {adjacent:.1%}  (écart <= 1 point)")
print(f"  Erreur abs. moy. : {mae:.2f} points")

# ---- borne haute : accord humain-humain ----
with_h2 = [r for r in main_run if r.get("human_score_2") is not None]
if with_h2:
    h1 = [int(r["human_score"]) for r in with_h2]
    h2 = [int(r["human_score_2"]) for r in with_h2]
    qwk_hh = quadratic_weighted_kappa(h1, h2, n_bins)
    print(f"\n=== Borne haute : correcteur 1 vs correcteur 2 ===")
    print(f"  QWK humain-humain : {qwk_hh:.3f}  (accord {interpret(qwk_hh)})")
    print(f"  Lecture : l'IA ne peut pas raisonnablement dépasser ce niveau.")

# ---- ventilation par confiance déclarée ----
print("\n=== Par niveau de confiance déclaré ===")
for level in ("high", "medium", "low"):
    sub = [r for r in main_run if r.get("confidence") == level]
    if len(sub) < 2:
        print(f"  {level:<7}: n={len(sub)} (trop peu)")
        continue
    ya = [to_int_scale(r["ai_score"], r["max_score"]) for r in sub]
    yh = [int(r["human_score"]) for r in sub]
    k = quadratic_weighted_kappa(ya, yh, n_bins)
    ks = f"{k:.3f}" if k is not None else "N/A"
    print(f"  {level:<7}: n={len(sub):<4} QWK={ks}")

# ---- stabilité inter-passages ----
runs = {}
for r in ok:
    runs.setdefault(r["item_id"], []).append(r)
multi = {k: v for k, v in runs.items() if len(v) > 1}
if multi:
    stds = [statistics.pstdev([float(x["ai_score"]) for x in v]) for v in multi.values()]
    identical = sum(1 for v in multi.values()
                    if len({to_int_scale(x["ai_score"], x["max_score"]) for x in v}) == 1)
    print(f"\n=== Stabilité inter-passages ({len(multi)} copies répétées) ===")
    print(f"  Écart-type moyen des scores : {statistics.mean(stds):.2f} points")
    print(f"  Copies avec score identique sur tous les passages : "
          f"{identical}/{len(multi)} ({identical / len(multi):.0%})")
    print(f"  Rappel (Chang & Ginter) : une faible variance ne garantit pas la justesse.")

# ---- lignes LaTeX ----
if args.latex:
    print("\n=== Lignes LaTeX pour le mémoire ===")
    print(f"QWK IA/humain & {qwk:.3f} ({interpret(qwk)}) \\\\")
    if with_h2:
        print(f"QWK humain/humain (borne haute) & {qwk_hh:.3f} \\\\")
    print(f"Accord exact & {exact:.1%} \\\\".replace("%", "\\%"))
    print(f"Accord adjacent & {adjacent:.1%} \\\\".replace("%", "\\%"))
    print(f"Erreur absolue moyenne & {mae:.2f} points \\\\")
