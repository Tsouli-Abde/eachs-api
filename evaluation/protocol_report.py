"""
protocol_report.py — Analyse la campagne Moodle du protocole EACHS.

Répond aux questions du chapitre de résultats à partir du seul journal d'audit :
- le routage applique-t-il le tableau de gouvernance (quel type déclenche la
  révision, et dans quelle proportion) ;
- le système discrimine-t-il les profils d'étudiants au sein d'un même type de
  tâche, et pas seulement les types entre eux ;
- la confiance déclarée par le modèle est-elle informative ;
- concordance IA / enseignant sur les copies effectivement révisées.

Le journal imposé par l'exigence de traçabilité sert ainsi d'instrument de
mesure : aucune instrumentation supplémentaire n'est nécessaire.

Usage :
    AUDIT_DB_PATH=data/audit_moodle.sqlite python evaluation/protocol_report.py [--latex]
"""

import argparse
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from audit import get_all_logs, quadratic_weighted_kappa  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--latex", action="store_true")
args = parser.parse_args()

TYPES = ["qcm", "short_answer", "essay", "formal"]
LIBELLE = {"qcm": "QCM", "short_answer": "Réponse courte",
           "essay": "Rédaction", "formal": "Exercice formel"}
# Régime attendu d'après le tableau de gouvernance du cadre.
REVISION_ATTENDUE = {"qcm": False, "short_answer": False,
                     "essay": True, "formal": True}

logs = [l for l in get_all_logs() if l["task_type"] in TYPES]
print(f"Base : {os.environ.get('AUDIT_DB_PATH', 'data/audit_log.sqlite')}")
print(f"{len(logs)} évaluations\n")
if not logs:
    sys.exit("Aucune évaluation : lancer le scheduler sur le terrain Moodle.")

backends = {l["backend"] for l in logs}
print(f"Backend(s) : {', '.join(sorted(backends))}\n")

# ── 1. Routage : le tableau de gouvernance est-il appliqué ? ────────────────
print("=== Routage par type de tâche ===")
print(f"{'Type':<16}{'n':>4}{'révision':>10}{'taux':>8}   régime attendu")
for t in TYPES:
    sub = [l for l in logs if l["task_type"] == t]
    if not sub:
        print(f"{LIBELLE[t]:<16}{0:>4}       —       —   (aucune copie)")
        continue
    rev = sum(1 for l in sub if l["requires_human_review"])
    attendu = "obligatoire" if REVISION_ATTENDUE[t] else "automatique sauf garde-fou"
    print(f"{LIBELLE[t]:<16}{len(sub):>4}{rev:>10}{rev / len(sub):>8.0%}   {attendu}")

# Écarts au régime attendu : une révision sur un type automatique doit
# s'expliquer par un garde-fou (confiance faible ou manipulation détectée).
print("\n--- Contrôle des écarts ---")
anomalies = 0
for t in TYPES:
    for l in [x for x in logs if x["task_type"] == t]:
        attendu = REVISION_ATTENDUE[t]
        reel = bool(l["requires_human_review"])
        if reel and not attendu:
            motif = []
            if l["confidence"] == "low":
                motif.append("confiance faible")
            if l["manipulation_detected"]:
                motif.append("manipulation détectée")
            if not motif:
                anomalies += 1
                print(f"  ANOMALIE {LIBELLE[t]} : révision sans garde-fou "
                      f"(log {l['log_id'][:8]})")
        elif attendu and not reel:
            anomalies += 1
            print(f"  ANOMALIE {LIBELLE[t]} : décision automatique alors que la "
                  f"révision est obligatoire (log {l['log_id'][:8]})")
if anomalies == 0:
    print("  Aucun écart : tout déclenchement hors régime nominal s'explique "
          "par un garde-fou, et aucune tâche à révision obligatoire n'y a échappé.")

# ── 2. Discrimination des profils ──────────────────────────────────────────
print("\n=== Score moyen par profil et par type (en % du barème) ===")
par_profil = defaultdict(lambda: defaultdict(list))
for l in logs:
    if l["max_score"]:
        nom = (l["student_name"] or f"Étudiant {l['student_id']}").strip()
        par_profil[nom][l["task_type"]].append(
            l["proposed_score"] / l["max_score"] * 100)

profils = sorted(par_profil)
entete = f"{'Profil':<20}" + "".join(f"{LIBELLE[t][:12]:>14}" for t in TYPES) + f"{'moyenne':>10}"
print(entete)
moyennes_profil = {}
for nom in profils:
    ligne = f"{nom:<20}"
    toutes = []
    for t in TYPES:
        vals = par_profil[nom][t]
        ligne += f"{statistics.mean(vals):>13.0f}%" if vals else f"{'—':>14}"
        toutes += vals
    if toutes:
        moyennes_profil[nom] = statistics.mean(toutes)
        ligne += f"{statistics.mean(toutes):>9.0f}%"
    print(ligne)

if len(moyennes_profil) >= 2:
    ordre = sorted(moyennes_profil.items(), key=lambda kv: -kv[1])
    ecart = ordre[0][1] - ordre[-1][1]
    print(f"\n  Écart entre le profil le mieux et le moins bien noté : {ecart:.0f} points de %")
    print(f"  Ordre obtenu : {' > '.join(n for n, _ in ordre)}")
    print("  Le dispositif discrimine les niveaux si cet ordre reproduit celui "
          "des personas (excellent > bon > moyen > faible).")

# ── 3. Confiance déclarée ──────────────────────────────────────────────────
print("\n=== Confiance déclarée par le modèle ===")
for t in TYPES:
    sub = [l for l in logs if l["task_type"] == t]
    if not sub:
        continue
    rep = defaultdict(int)
    for l in sub:
        rep[l["confidence"]] += 1
    detail = "  ".join(f"{k}={v}" for k, v in sorted(rep.items()))
    print(f"  {LIBELLE[t]:<16} {detail}")

# ── 4. Concordance sur les copies révisées ─────────────────────────────────
revises = [l for l in logs
           if l["human_final_score"] is not None
           and l["human_decision"] != "rejected"
           and l["max_score"]]
print(f"\n=== Concordance IA / enseignant ===")
if len(revises) < 2:
    print(f"  {len(revises)} copie(s) révisée(s) : pas encore de quoi calculer "
          f"un kappa. Réviser les copies en attente dans le tableau de bord.")
else:
    def classe(score, maxi):
        """Cinq classes de 20 % du barème, comme l'endpoint /stats/kappa."""
        return min(4, int(score / maxi * 5)) if maxi else 0

    y_ia = [classe(l["proposed_score"], l["max_score"]) for l in revises]
    y_hu = [classe(l["human_final_score"], l["max_score"]) for l in revises]
    k = quadratic_weighted_kappa(y_ia, y_hu, 5)
    ecarts = [abs(l["proposed_score"] - l["human_final_score"]) / l["max_score"] * 100
              for l in revises]
    modifs = sum(1 for l in revises if l["human_decision"] == "modified")
    print(f"  n = {len(revises)} paires")
    print(f"  QWK                    : {k:.3f}" if k is not None else "  QWK : non calculable")
    print(f"  Taux de modification   : {modifs / len(revises):.0%}")
    print(f"  Écart absolu moyen     : {statistics.mean(ecarts):.1f} points de %")
    rejets = sum(1 for l in logs if l["human_decision"] == "rejected")
    if rejets:
        print(f"  ({rejets} copie(s) rejetée(s), exclue(s) : un rejet n'est pas "
              f"un désaccord de note)")

en_attente = sum(1 for l in logs if l["requires_human_review"] and not l["human_decision"])
if en_attente:
    print(f"\n  {en_attente} copie(s) en attente de révision dans le tableau de bord.")

# ── 5. Sorties LaTeX ───────────────────────────────────────────────────────
if args.latex:
    print("\n=== Lignes LaTeX : routage par type ===")
    for t in TYPES:
        sub = [l for l in logs if l["task_type"] == t]
        if not sub:
            continue
        rev = sum(1 for l in sub if l["requires_human_review"])
        moy = statistics.mean([l["proposed_score"] / l["max_score"] * 100
                               for l in sub if l["max_score"]])
        print(f"{LIBELLE[t]} & {len(sub)} & {rev} & {rev / len(sub):.0%} & {moy:.0f}\\% \\\\")
