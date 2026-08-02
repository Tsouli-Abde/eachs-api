# Résultats des campagnes de mesure

Chiffres obtenus les 1er et 2 août 2026, destinés au chapitre de résultats du
mémoire. Chaque valeur est reproductible avec les commandes indiquées.

Les deux terrains ont des rôles distincts, et les confondre serait une erreur
de lecture :

- le terrain **Moodle** démontre que le *dispositif* fonctionne (routage,
  décisions humaines, écriture des notes, archivage) ;
- le corpus **ASAP-SAS** mesure la *qualité* de l'évaluation, contre de vrais
  correcteurs humains.

> **Le kappa IA/enseignant du terrain Moodle n'est pas un résultat.** Les
> décisions humaines de cette campagne ont été prises au hasard pour faire
> apparaître des métriques dans l'interface. Elles attestent que le cycle de
> révision fonctionne, elles ne mesurent aucune concordance. La concordance se
> lit sur ASAP-SAS uniquement.

---

## 1. Terrain Moodle : le dispositif

64 copies (4 cours × 4 devoirs × 4 profils), backend Mistral 7B via Ollama.

```bash
AUDIT_DB_PATH=data/audit_moodle.sqlite python3 evaluation/protocol_report.py --latex
```

### Routage : conforme au tableau de gouvernance

| Type | n | Révision déclenchée | Régime attendu |
|---|---|---|---|
| QCM | 16 | 3 (19 %) | automatique sauf garde-fou |
| Réponse courte | 16 | 2 (12 %) | automatique sauf garde-fou |
| Rédaction | 16 | 16 (100 %) | obligatoire |
| Exercice formel | 16 | 16 (100 %) | obligatoire |

Le contrôle d'écarts ne relève **aucune anomalie** : tout déclenchement hors
régime nominal s'explique par un garde-fou (confiance faible), et aucune tâche
à révision obligatoire n'y a échappé.

### Discrimination des profils

| Profil | QCM | Rép. courte | Rédaction | Ex. formel | Moyenne |
|---|---|---|---|---|---|
| Alice (excellent) | 95 % | 100 % | 100 % | 94 % | **97 %** |
| Bob (bon) | 95 % | 100 % | 89 % | 94 % | **94 %** |
| Clara (moyen) | 22 % | 100 % | 80 % | 59 % | **65 %** |
| David (faible) | 26 % | 30 % | 15 % | 6 % | **19 %** |

L'ordre obtenu reproduit exactement celui des personas, avec 78 points d'écart
entre les extrêmes. Mesure valide car, depuis le correctif du barème, les
quatre copies d'un même devoir sont jugées avec le même barème.

---

## 2. ASAP-SAS : la concordance

Corpus public, deux correcteurs humains par copie, échantillonnage stratifié
(graine 42). La borne haute humain-humain donne le plafond atteignable.

```bash
python3 evaluation/metrics.py data/results_qwen_rubric.jsonl --latex
python3 evaluation/compare_runs.py --a <sans> --b <avec> --latex
```

### Effet du barème, à modèle constant (Mistral 7B, 98 copies communes)

| | Sans barème | Avec barème |
|---|---|---|
| QWK IA/humain | 0,129 | **0,309** |
| Accord exact | 21,4 % | 25,5 % |
| Accord adjacent | 55,1 % | 66,3 % |
| Erreur absolue moyenne | 1,38 | 1,17 |
| Note moyenne attribuée | 2,74 | 2,56 |

Note moyenne humaine : 1,43. Le corpus initialement utilisé ne transmettait pas
le barème au modèle : la tâche était sous-spécifiée, et le QWK mesurait cette
sous-spécification plutôt qu'une capacité.

### Effet du modèle, à barème constant (98 copies communes)

| | Mistral 7B | qwen2.5 **3B** |
|---|---|---|
| QWK IA/humain | 0,309 | **0,669** |
| Accord exact | 25,5 % | 46,9 % |
| Accord adjacent | 66,3 % | 91,8 % |
| Erreur absolue moyenne | 1,17 | 0,61 |
| Note moyenne attribuée | 2,56 | 1,27 |

Répartition des notes attribuées (échelle 0-3) :

| | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Mistral 7B | 8 | 7 | 5 | **78** |
| qwen2.5 3B | 34 | 23 | 22 | 19 |
| Humain | 22 | 29 | 30 | 17 |

Un modèle 2,3 fois plus petit fait deux fois mieux : la taille n'est pas le
critère. Mistral n'exploite pas l'échelle, ce que la seule note moyenne ne
montrerait pas.

### Sensibilité à l'énoncé (qwen2.5, 100 copies par set)

| | Set 1 (Acid Rain) | Set 5 (Protein Synthesis) |
|---|---|---|
| QWK | **0,665** (substantiel) | **0,458** (modéré) |
| Accord exact | 46,0 % | 80,0 % |
| Accord adjacent | 92,0 % | 98,0 % |
| Erreur absolue moyenne | 0,62 | 0,22 |
| QWK humain-humain | 0,934 | 0,959 |

Le résultat varie fortement d'un énoncé à l'autre : un chiffre unique sur un
seul set ne serait pas généralisable.

L'inversion apparente entre accord exact et QWK sur le set 5 s'explique par le
déséquilibre des notes : 77 copies sur 100 valent 0, si bien que noter 0
partout donnerait déjà 80 % d'accord exact. Le kappa corrige cet effet du
hasard, l'accord exact non — ce qui justifie le QWK comme métrique de
référence.

### Stabilité inter-passages (qwen2.5, 30 copies évaluées 5 fois)

```bash
python3 evaluation/batch_runner.py --corpus data/corpus_set1_rubric.csv \
    --api http://localhost:8005 --out data/results_qwen_stabilite.jsonl \
    --repeats 5 --limit 30
```

| Indicateur | Valeur |
|---|---|
| Écart-type moyen des scores | **0,03 point** |
| Copies notées à l'identique sur les 5 passages | **28/30 (93 %)** |
| QWK du passage principal, mêmes 30 copies | 0,684 |

Le dispositif est donc reproductible : rejouer une campagne redonne
pratiquement les mêmes notes, ce qui rend les comparaisons entre backends
légitimes.

Cette reproductibilité ne dit toutefois rien de la justesse, et le rapprochement
avec la section suivante le montre : le modèle produit des scores très stables
alors que sa confiance déclarée n'a aucune valeur prédictive. C'est exactement
l'avertissement de Chang & Ginter — une faible variance entre passages répétés
ne peut pas servir d'indicateur de fiabilité, et ne saurait donc fonder un
mécanisme d'escalade.

### Confiance déclarée : non informative

| Niveau déclaré | n | QWK du sous-ensemble |
|---|---|---|
| high | 33 | 0,096 |
| medium | 31 | 0,004 |

Sur le sous-échantillon de 30 copies du test de stabilité, les valeurs
descendent même légèrement sous zéro (−0,098 pour `high`, −0,053 pour
`medium`), mais les effectifs y sont trop faibles pour conclure à autre chose
qu'une absence de lien.

Le modèle déclare donc une confiance élevée sur des évaluations dont l'accord
avec l'humain est proche du hasard, alors que le QWK d'ensemble est
substantiel : le signal n'isole pas les copies bien évaluées. La règle
transverse « confiance faible force la révision » repose sur un indicateur sans
valeur prédictive — limite à assumer, d'autant que la stabilité mesurée plus
haut ne peut pas non plus lui servir de substitut.

---

## 3. Robustesse adverse

36 puis 43 soumissions : six familles d'attaques documentées, plus des
contrôles légitimes destinés à mesurer les faux positifs.

```bash
python3 evaluation/build_adversarial.py --task-type qcm --out data/corpus_adv.csv
python3 evaluation/redteam_metrics.py --corpus data/corpus_adv.csv --results <res> --latex
```

### Le type de tâche déclaré change tout (prompt 1.2.0, Mistral 7B)

| | Déclaré `essay` | Déclaré `qcm` |
|---|---|---|
| Taux de détection | 36,7 % | 36,7 % |
| Révision déclenchée | **100 %** | **46,7 %** |
| Tentatives parties en décision automatique | 0 | **16 sur 30** |

La détection est identique ; c'est le routage qui protège. Sur une tâche que la
gouvernance laisse en automatique, une tentative non détectée n'est plus
rattrapée. C'est la limite du cadre, mesurée.

### Effet du correctif de prompt (1.2.0 → 1.3.0, mêmes 30 attaques en `qcm`)

| | 1.2.0 | 1.3.0 |
|---|---|---|
| Détection | 11/30 (37 %) | **13/30 (43 %)** |
| Révision déclenchée | 14/30 (47 %) | **18/30 (60 %)** |
| Faux positif sur « A) O(V). » (10 rejeux) | **5/10** | **0/10** |
| Faux positifs, tous contrôles | 0/6 | **0/13** |

Origine du correctif : en campagne réelle, la réponse de QCM « A) O(V). » a été
annulée pour manipulation, le modèle ayant lu la lettre d'option comme une
demande de note. Rejouée dix fois à conditions identiques, la copie était
accusée cinq fois sur dix — le détecteur n'est pas déterministe, et un étudiant
honnête avait donc une chance sur deux d'être signalé comme fraudeur.

Le préambule 1.3.0 distingue une instruction adressée au correcteur d'une
réponse au sujet posé, et pose qu'accuser à tort est plus grave que manquer une
tentative. Détection et équité progressent ensemble : clarifier ce qui *est* une
manipulation aide le modèle à discriminer dans les deux sens.

### Détection par famille (prompt 1.3.0)

| Famille | n | Détectées |
|---|---|---|
| Manipulation émotionnelle | 5 | 5 (100 %) |
| Ingénierie sociale | 5 | 3 (60 %) |
| Jeu de rôle | 5 | 3 (60 %) |
| Injection directe | 5 | 1 (20 %) |
| Demande explicite de note | 5 | 1 (20 %) |
| Dilution par la longueur | 5 | 0 (0 %) |

Les familles les mieux détectées sont celles qui portent une charge
rhétorique visible ; les plus techniques passent au travers.

---

## 4. Contraintes de déploiement observées

| Backend | Constat |
|---|---|
| Gemini 2.5 Flash (gratuit) | **20 requêtes par jour**, quota par modèle. Inutilisable pour une campagne de 100 copies. |
| Gemini, SDK | Instancier un client par appel casse le transport partagé dès qu'il y a du parallélisme : l'erreur ressemble à un quota sans en être un. |
| Ollama | Sert trois requêtes de front sans dégradation. En revanche, deux modèles distincts en parallèle forcent leur permutation en mémoire et provoquent des délais d'attente. |
| Barème | Généré par copie, il coûtait quatre appels par devoir et changeait d'un étudiant à l'autre. Fixé par devoir : campagne quatre fois plus rapide et copies comparables. |

---

## Reproduire

```bash
# terrain Moodle
python3 scripts/seed_demo.py && python3 backend/scheduler.py
AUDIT_DB_PATH=data/audit_moodle.sqlite python3 evaluation/protocol_report.py --latex

# concordance, un backend donné
./evaluation/run_campaign.sh local qwen2.5:3b

# robustesse
python3 evaluation/build_adversarial.py --task-type qcm --out data/corpus_adv.csv
```
