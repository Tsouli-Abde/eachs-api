"""
seed_students.py — Crée des étudiants avec profils contrastés et soumet leurs réponses.
Lance avec : python3 seed_students.py
"""
import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL = os.environ.get("MOODLE_URL", "http://localhost:8080")
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN")
ADMIN_USER = os.environ.get("MOODLE_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("MOODLE_ADMIN_PASSWORD", "Admin1234!")

# ─── Profils étudiants ────────────────────────────────────────────────

STUDENTS = [
    {
        "username": "alice_martin",
        "password": "Alice1234!",
        "firstname": "Alice",
        "lastname": "Martin",
        "email": "alice@eachs.local",
        "profile": "excellent",
        "description": "Excellente étudiante — réponses complètes, précises, avec exemples",
    },
    {
        "username": "bob_dupont",
        "password": "Bob1234!",
        "firstname": "Bob",
        "lastname": "Dupont",
        "email": "bob@eachs.local",
        "profile": "good",
        "description": "Bon étudiant — réponses correctes mais manque parfois de profondeur",
    },
    {
        "username": "clara_rousseau",
        "password": "Clara1234!",
        "firstname": "Clara",
        "lastname": "Rousseau",
        "email": "clara@eachs.local",
        "profile": "average",
        "description": "Étudiante moyenne — comprend les concepts mais formulation imprécise",
    },
    {
        "username": "david_petit",
        "password": "David1234!",
        "firstname": "David",
        "lastname": "Petit",
        "email": "david@eachs.local",
        "profile": "weak",
        "description": "Étudiant en difficulté — réponses incomplètes ou hors sujet",
    },
]

# ─── Réponses par profil et par devoir ────────────────────────────────

RESPONSES = {
    # IA-M2
    "Devoir 1 — Algorithmes de recherche": {
        "excellent": "BFS (Breadth-First Search) explore le graphe niveau par niveau en utilisant une file FIFO, ce qui garantit de trouver le chemin le plus court dans un graphe non pondéré. Sa complexité est O(V+E). DFS (Depth-First Search) utilise une pile LIFO et explore en profondeur avant de revenir en arrière, avec une complexité O(V+E). On privilégie BFS pour trouver le plus court chemin ou explorer des graphes peu profonds, et DFS pour détecter des cycles, effectuer un tri topologique, ou explorer des graphes profonds avec peu de branches. Par exemple, BFS est idéal pour le problème du plus court chemin dans un réseau social, tandis que DFS est préféré pour résoudre un labyrinthe ou générer un arbre couvrant.",
        "good": "BFS explore niveau par niveau avec une file et garantit le chemin le plus court dans un graphe non pondéré. DFS utilise une pile et va en profondeur avant de revenir. On utilise BFS quand on cherche le chemin le plus court et DFS pour explorer toutes les solutions possibles. BFS consomme plus de mémoire que DFS car il stocke tous les nœuds d'un niveau.",
        "average": "BFS et DFS sont deux algorithmes de recherche dans un graphe. BFS utilise une queue et DFS une stack. BFS est meilleur pour les graphes peu profonds et DFS pour les graphes profonds. La différence principale est que BFS va en largeur et DFS en profondeur.",
        "weak": "BFS cherche en largeur et DFS en profondeur. BFS utilise une file et DFS une pile. Je ne sais pas vraiment quand utiliser l'un ou l'autre mais je crois que BFS est plus lent.",
    },
    "Devoir 2 — Réseaux de neurones": {
        "excellent": "La rétropropagation du gradient est un algorithme fondamental qui permet d'entraîner les réseaux de neurones profonds. Elle calcule le gradient de la fonction de perte par rapport à chaque poids du réseau en appliquant la règle de dérivation en chaîne de manière récursive, de la couche de sortie vers les couches d'entrée. Pour chaque paramètre w, on calcule ∂L/∂w, puis on met à jour w ← w - η·∂L/∂w où η est le taux d'apprentissage. Sans rétropropagation, il serait impossible d'optimiser efficacement les millions de paramètres d'un réseau profond. Elle permet au réseau de corriger ses erreurs en ajustant proportionnellement chaque poids à sa contribution à l'erreur totale.",
        "good": "La rétropropagation calcule le gradient de la perte par rapport aux poids en utilisant la règle de la chaîne. Elle propage l'erreur de la couche de sortie vers les couches d'entrée. Pour chaque poids, elle calcule sa contribution à l'erreur et le met à jour dans la direction opposée au gradient. C'est ce qui permet au réseau d'apprendre à partir des données d'entraînement en minimisant progressivement l'erreur.",
        "average": "La rétropropagation permet d'ajuster les poids d'un réseau de neurones. Elle calcule les erreurs et les propage vers l'arrière pour corriger les poids. C'est important pour l'entraînement car sans ça le réseau ne peut pas apprendre.",
        "weak": "La rétropropagation sert à entraîner les réseaux de neurones. Elle calcule les erreurs et les corrige. Je ne comprends pas très bien comment ça marche mathématiquement.",
    },
    "Examen — Overfitting et régularisation": {
        "excellent": "Le surapprentissage (overfitting) survient quand un modèle apprend les détails et le bruit des données d'entraînement au point de ne plus généraliser sur de nouvelles données. Il se manifeste par une faible erreur d'entraînement et une erreur de test élevée. Causes principales : modèle trop complexe par rapport à la quantité de données, données d'entraînement insuffisantes, ou entraînement trop long. Pour l'éviter : (1) Régularisation L1/L2 qui ajoute une pénalité sur la magnitude des poids, forçant le modèle à apprendre des représentations plus simples ; (2) Dropout qui désactive aléatoirement des neurones pendant l'entraînement, forçant la redondance. D'autres méthodes incluent l'early stopping et l'augmentation de données.",
        "good": "L'overfitting se produit quand le modèle mémorise les données d'entraînement sans généraliser. Cela donne une bonne performance sur train mais mauvaise sur test. Les causes sont un modèle trop complexe et peu de données. Pour l'éviter : la régularisation L2 pénalise les grands poids, et le dropout désactive aléatoirement des neurones pendant l'entraînement, ce qui force le réseau à apprendre des features robustes.",
        "average": "L'overfitting c'est quand le modèle apprend trop bien les données d'entraînement. Il ne généralise pas bien sur les nouvelles données. Pour éviter ça on peut utiliser la régularisation ou le dropout.",
        "weak": "L'overfitting c'est quand le modèle est trop précis sur les données d'entraînement. C'est un problème car il ne marche pas bien en production. Je pense qu'on peut utiliser plus de données pour éviter ça.",
    },
    # BDA-M2
    "Examen — Transactions et ACID": {
        "excellent": "Les propriétés ACID garantissent la fiabilité des transactions dans un SGBD. Atomicité : une transaction est exécutée entièrement ou annulée, jamais partiellement. Exemple : un virement débitant le compte A et créditant B s'exécute entièrement ou pas du tout. Cohérence : la base transite d'un état valide à un autre, respectant toutes les contraintes d'intégrité. Exemple : une contrainte de solde ≥ 0 est respectée. Isolation : les transactions concurrentes s'exécutent comme si elles étaient séquentielles, sans interférence. Exemple : deux réservations simultanées du dernier siège ne peuvent pas aboutir toutes les deux. Durabilité : une transaction validée persiste même en cas de panne système, grâce au journal WAL (Write-Ahead Log).",
        "good": "ACID : Atomicité (tout ou rien, ex: virement bancaire), Cohérence (la base reste dans un état valide, ex: les contraintes sont respectées), Isolation (les transactions ne se voient pas mutuellement, ex: deux achats simultanés du dernier article), Durabilité (les données persistent après validation, ex: même après un crash serveur). Ces propriétés sont essentielles pour les systèmes critiques comme les systèmes bancaires.",
        "average": "ACID signifie Atomicité, Cohérence, Isolation et Durabilité. L'atomicité signifie tout ou rien. La cohérence garde la base dans un bon état. L'isolation évite les problèmes de concurrence. La durabilité assure que les données sont sauvegardées.",
        "weak": "ACID c'est des propriétés des bases de données. A c'est atomique, C cohérent, I isolé, D durable. Je ne me souviens pas bien des exemples pour chacun.",
    },
    "TP — Optimisation des requêtes": {
        "excellent": "Un index est une structure de données auxiliaire (généralement un B-tree ou un hash) qui permet d'accéder rapidement aux lignes d'une table sans effectuer de scan complet. Il améliore les performances des requêtes SELECT avec des conditions WHERE, ORDER BY ou JOIN en réduisant la complexité de O(n) à O(log n). Inconvénients : (1) Surcoût en écriture — chaque INSERT, UPDATE, DELETE doit mettre à jour l'index en plus de la table, ralentissant ces opérations ; (2) Espace disque supplémentaire ; (3) Choix inadapté peut dégrader les performances (ex: index sur une colonne à faible cardinalité). La stratégie optimale consiste à indexer les colonnes fréquemment utilisées dans les clauses WHERE et les clés étrangères.",
        "good": "Un index crée une structure de données supplémentaire pour accélérer les recherches. Il améliore les SELECT en évitant le full table scan mais ralentit les INSERT, UPDATE et DELETE car l'index doit être mis à jour. Il consomme aussi de l'espace disque. Le type le plus courant est le B-tree qui offre une complexité O(log n) pour les recherches.",
        "average": "Un index accélère les recherches dans une base de données. Il améliore les performances mais prend de la place. Il ralentit les insertions car il faut mettre à jour l'index en plus de la table.",
        "weak": "Un index c'est quelque chose qui rend les requêtes plus rapides. Il y a des avantages et des inconvénients mais je ne me rappelle plus bien lesquels.",
    },
    "Devoir — Modélisation UML": {
        "excellent": "Le diagramme de classes modélise la structure statique du système : les classes, leurs attributs, méthodes et relations (associations, agrégations, compositions, héritages). Il répond à 'comment est structuré le système ?' et est central lors de la conception. Le diagramme de séquence modélise les interactions dynamiques entre objets dans le temps, montrant les échanges de messages dans un scénario précis. Il répond à 'comment les objets collaborent-ils pour réaliser un cas d'utilisation ?' On utilise le diagramme de classes pour concevoir l'architecture du logiciel et documenter le modèle de données, et le diagramme de séquence pour modéliser un scénario d'utilisation, valider une architecture ou documenter un protocole de communication.",
        "good": "Le diagramme de classes représente la structure statique : classes, attributs, méthodes et relations entre classes. Il est utilisé pour concevoir l'architecture. Le diagramme de séquence représente les interactions dynamiques entre objets dans le temps, montrant comment les objets s'échangent des messages. On l'utilise pour modéliser un scénario fonctionnel ou un cas d'utilisation.",
        "average": "Le diagramme de classes montre les classes et leurs relations. Le diagramme de séquence montre comment les objets interagissent. Le diagramme de classes est statique et le diagramme de séquence est dynamique.",
        "weak": "Ce sont deux types de diagrammes UML. Un montre les classes et l'autre montre les séquences. Je ne suis pas sûr de la différence exacte entre les deux.",
    },
    # GL-L3
    "Quiz — Patrons de conception": {
        "excellent": "Le patron Singleton est un patron créationnel qui garantit qu'une classe ne possède qu'une seule instance dans toute l'application et fournit un point d'accès global à cette instance. Il s'implémente en rendant le constructeur privé, en déclarant un attribut statique privé de type instance, et en exposant une méthode statique publique getInstance() qui crée l'instance si elle n'existe pas et la retourne sinon. Cas d'utilisation typiques : gestionnaire de configuration, pool de connexions à une base de données, logger centralisé, cache applicatif. Limitation importante : il rend le code difficile à tester unitairement car il introduit un état global partagé, et peut causer des problèmes de concurrence en environnement multi-thread sans synchronisation.",
        "good": "Le Singleton assure qu'une classe n'a qu'une seule instance et donne un accès global à cette instance. Il s'implémente avec un constructeur privé et une méthode statique getInstance(). On l'utilise pour les ressources partagées comme les connexions à une base de données ou les fichiers de configuration. L'inconvénient est qu'il est difficile à tester et peut causer des problèmes en multi-thread.",
        "average": "Le Singleton garantit une seule instance d'une classe. On l'utilise pour les ressources partagées. Il s'implémente avec un constructeur privé. C'est utile pour éviter d'avoir plusieurs connexions à la base de données.",
        "weak": "Le Singleton c'est un design pattern qui fait qu'une classe a une seule instance. Je pense que c'est utile pour économiser des ressources.",
    },
    "Devoir — Qualité du code": {
        "excellent": "La dette technique désigne l'ensemble des compromis techniques acceptés délibérément pour livrer plus vite, qui génèrent un coût de maintenance croissant dans le futur — par analogie avec une dette financière portant intérêts. Causes principales : pression temporelle imposant des solutions rapides mais imparfaites, manque de documentation, tests insuffisants, refactoring reporté, ou mauvaises pratiques accumulées. Conséquences : ralentissement progressif des développements, augmentation du taux de bugs, difficulté à onboarder de nouveaux développeurs, rigidité du code face aux évolutions. Gestion : mesurer via des outils comme SonarQube, prioriser le remboursement dans chaque sprint (règle du Boy Scout : laisser le code plus propre qu'on ne l'a trouvé), planifier des sprints dédiés au refactoring, et mettre en place des revues de code systématiques.",
        "good": "La dette technique représente le coût des compromis techniques faits pour aller plus vite. Elle est causée par la pression temporelle, le manque de tests et les mauvaises pratiques. Elle entraîne un ralentissement des développements et une accumulation de bugs. On la gère avec des revues de code régulières, du refactoring planifié et des sprints dédiés à la qualité.",
        "average": "La dette technique c'est quand on écrit du mauvais code pour aller plus vite. Ça cause des problèmes plus tard car le code est difficile à maintenir. On peut la réduire en faisant du refactoring.",
        "weak": "La dette technique c'est quand on a beaucoup de code à refaire. C'est causé par le manque de temps. C'est difficile à gérer.",
    },
    "Examen — Tests logiciels": {
        "excellent": "Les tests unitaires vérifient le comportement d'une unité de code isolée (fonction, méthode, classe) en mockant ses dépendances. Exemple : tester qu'une fonction calculateTVA(100, 0.2) retourne 20. Les tests d'intégration vérifient la collaboration entre plusieurs composants réels sans mock. Exemple : tester que le service de commande interagit correctement avec le repository de base de données. Les tests end-to-end (E2E) simulent le parcours complet d'un utilisateur à travers l'application complète. Exemple : tester le processus d'achat depuis la navigation produit jusqu'à la confirmation de paiement via Selenium ou Cypress. La pyramide de tests recommande beaucoup de tests unitaires (rapides, peu coûteux), quelques tests d'intégration, et peu de tests E2E (lents, fragiles).",
        "good": "Tests unitaires : vérifient une fonction isolée, ex: tester une fonction de calcul de TVA. Tests d'intégration : vérifient l'interaction entre composants, ex: tester le service de paiement avec la base de données. Tests E2E : simulent le parcours complet d'un utilisateur, ex: tester le processus d'achat complet. La pyramide de tests conseille plus de tests unitaires que d'intégration et plus d'intégration que d'E2E.",
        "average": "Les tests unitaires testent une petite partie du code. Les tests d'intégration testent plusieurs composants ensemble. Les tests end-to-end testent toute l'application. Les tests unitaires sont les plus rapides et les tests E2E les plus lents.",
        "weak": "Il y a plusieurs types de tests. Les tests unitaires testent des petites choses, les tests d'intégration testent plus de choses ensemble, et les tests end-to-end testent tout. Je ne suis pas sûr des différences exactes.",
    },
}

# ─── API REST ────────────────────────────────────────────────────────

def api(function, params, method="GET"):
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    params.update({"wstoken": MOODLE_TOKEN, "wsfunction": function, "moodlewsrestformat": "json"})
    r = requests.post(url, data=params, timeout=30) if method == "POST" else requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    if not r.text.strip():
        return True
    result = r.json()
    if isinstance(result, dict) and "exception" in result:
        return None
    return result

# ─── Session web ─────────────────────────────────────────────────────

def get_session(username, password):
    session = requests.Session()
    r = session.get(f"{MOODLE_URL}/login/index.php", timeout=30)
    token_match = re.search(r'name="logintoken".*?value="([^"]+)"', r.text)
    logintoken = token_match.group(1) if token_match else ""
    session.post(f"{MOODLE_URL}/login/index.php", data={
        "username": username, "password": password, "logintoken": logintoken
    }, allow_redirects=True, timeout=30)
    return session

def get_sesskey(session):
    r = session.get(f"{MOODLE_URL}/my/", timeout=30)
    m = re.search(r'"sesskey":"([^"]+)"', r.text)
    return m.group(1) if m else ""

# ─── Fonctions Moodle ─────────────────────────────────────────────────

def create_student(student):
    # Vérifier si l'utilisateur existe déjà
    existing = api("core_user_get_users", {
        "criteria[0][key]": "username",
        "criteria[0][value]": student["username"]
    })
    if existing and existing.get("users"):
        uid = existing["users"][0]["id"]
        print(f"  Utilisateur existant : [{uid}] {student['firstname']} {student['lastname']}")
        return uid

    result = api("core_user_create_users", {
        "users[0][username]": student["username"],
        "users[0][password]": student["password"],
        "users[0][firstname]": student["firstname"],
        "users[0][lastname]": student["lastname"],
        "users[0][email]": student["email"],
        "users[0][auth]": "manual",
    }, method="POST")

    if result and len(result) > 0:
        uid = result[0]["id"]
        print(f"  Créé : [{uid}] {student['firstname']} {student['lastname']} ({student['profile']})")
        return uid
    return None

def enroll_student(course_id, user_id):
    api("enrol_manual_enrol_users", {
        "enrolments[0][roleid]": 5,
        "enrolments[0][userid]": user_id,
        "enrolments[0][courseid]": course_id,
    }, method="POST")

def get_all_courses():
    result = api("core_course_get_courses", {})
    if isinstance(result, list):
        return [c for c in result if c.get("id", 0) > 1]
    return []

def get_assignments(course_id):
    result = api("mod_assign_get_assignments", {"courseids[0]": course_id})
    courses = result.get("courses", [])
    if not courses:
        return []
    return courses[0].get("assignments", [])

def has_submission(assignment_id, user_id):
    result = api("mod_assign_get_submissions", {"assignmentids[0]": assignment_id})
    if result:
        for a in result.get("assignments", []):
            for s in a.get("submissions", []):
                if s.get("userid") == user_id and s.get("status") == "submitted":
                    return True
    return False

def submit_as_student(student, assignment_id, assignment_name):
    """Soumet une réponse en tant qu'étudiant via session web."""
    response_text = RESPONSES.get(assignment_name, {}).get(student["profile"])
    if not response_text:
        print(f"    Pas de réponse définie pour {student['profile']} sur '{assignment_name}'")
        return False

    session = get_session(student["username"], student["password"])
    sesskey = get_sesskey(session)

    # Trouver le cmid du devoir
    r = session.get(f"{MOODLE_URL}/mod/assign/view.php?action=editsubmission", timeout=30)

    # Chercher directement via l'URL du devoir
    courses = get_all_courses()
    cmid = None
    for course in courses:
        contents = api("core_course_get_contents", {"courseid": course["id"]})
        if not contents:
            continue
        for section in contents:
            for mod in section.get("modules", []):
                if mod.get("modname") == "assign" and mod.get("name") == assignment_name:
                    url = mod.get("url", "")
                    m = re.search(r'id=(\d+)', url)
                    if m:
                        cmid = int(m.group(1))
                        break
            if cmid:
                break
        if cmid:
            break

    if not cmid:
        print(f"    cmid introuvable pour '{assignment_name}'")
        return False

    r = session.get(f"{MOODLE_URL}/mod/assign/view.php?id={cmid}&action=editsubmission", timeout=30)
    hidden_fields = {}
    for match in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', r.text, re.IGNORECASE):
        tag = match.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag)
        value_m = re.search(r'value=["\']([^"\']*)["\']', tag)
        if name_m:
            hidden_fields[name_m.group(1)] = value_m.group(1) if value_m else ""

    data = dict(hidden_fields)
    data.update({
        "_qf__mod_assign_submission_form": "1",
        "mform_isexpanded_id_onlinetextsubmission": "1",
        "onlinetext_editor[text]": response_text,
        "onlinetext_editor[format]": "1",
        "onlinetext_editor[itemid]": hidden_fields.get("onlinetext_editor[itemid]", "0"),
        "action": "savesubmission",
    })

    r2 = session.post(f"{MOODLE_URL}/mod/assign/view.php?id={cmid}", data=data, timeout=30, allow_redirects=True)
    return r2.status_code == 200

# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Seed étudiants EACHS ===\n")

    courses = get_all_courses()
    if not courses:
        print("Aucun cours trouvé. Lance seed_complete.py d'abord.")
        exit(1)

    print(f"Cours trouvés : {[c['shortname'] for c in courses]}\n")

    total_students = total_enrollments = total_submissions = 0

    # 1. Créer les étudiants
    print("─── Création des étudiants ───")
    student_ids = {}
    for student in STUDENTS:
        uid = create_student(student)
        if uid:
            student_ids[student["username"]] = uid
            total_students += 1

    print(f"\n{total_students} étudiant(s) prêt(s)\n")

    # 2. Inscrire chaque étudiant dans tous les cours
    print("─── Inscriptions ───")
    for course in courses:
        course_id = course["id"]
        course_name = course.get("shortname", str(course_id))
        for student in STUDENTS:
            uid = student_ids.get(student["username"])
            if uid:
                enroll_student(course_id, uid)
                total_enrollments += 1
        print(f"  {course_name} — {len(STUDENTS)} étudiants inscrits")

    print(f"\n{total_enrollments} inscription(s) effectuée(s)\n")

    # 3. Soumettre les réponses
    print("─── Soumissions ───")
    for course in courses:
        course_id = course["id"]
        course_name = course.get("shortname")
        assignments = get_assignments(course_id)
        print(f"\n[{course_name}]")

        for assignment in assignments:
            assignment_id = assignment["id"]
            assignment_name = assignment["name"]
            print(f"  Devoir : {assignment_name}")

            if assignment_name not in RESPONSES:
                print(f"    Pas de réponses définies pour ce devoir, on passe.")
                continue

            for student in STUDENTS:
                uid = student_ids.get(student["username"])
                if not uid:
                    continue

                if has_submission(assignment_id, uid):
                    print(f"    [{student['profile']:8}] {student['firstname']:6} — soumission existante")
                    continue

                print(f"    [{student['profile']:8}] {student['firstname']:6} — soumission en cours...", end=" ")
                ok = submit_as_student(student, assignment_id, assignment_name)
                if ok:
                    print("✓")
                    total_submissions += 1
                else:
                    print("✗")
                time.sleep(0.5)

    print(f"\n=== Terminé ===")
    print(f"Étudiants : {total_students} | Inscriptions : {total_enrollments} | Soumissions : {total_submissions}")
    print(f"\nLance le scheduler pour évaluer automatiquement :")
    print(f"  python3 scheduler.py")