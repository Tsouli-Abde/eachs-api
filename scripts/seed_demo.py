"""
seed_demo.py — Recrée cours, devoirs, étudiants et soumissions
avec une répartition équilibrée des 4 types de tâches EACHS.

Répartition cible :
  QCM          : 25%  — 4 devoirs QCM
  Réponse courte: 25%  — 4 devoirs short_answer
  Rédaction    : 25%  — 4 devoirs essay
  Formel       : 25%  — 4 devoirs formal

Usage : python seed_demo.py
"""

import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL   = os.environ.get("MOODLE_URL",   "http://localhost:8080")
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN")
MOODLE_USER  = os.environ.get("MOODLE_ADMIN_USER",     "admin")
MOODLE_PASS  = os.environ.get("MOODLE_ADMIN_PASSWORD", "Admin1234!")

# ── helpers ──────────────────────────────────────────────────────────────────

def api(fn, params, method="GET"):
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    params.update({"wstoken": MOODLE_TOKEN, "wsfunction": fn, "moodlewsrestformat": "json"})
    r = requests.request(method, url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "exception" in data:
        raise RuntimeError(f"{fn} → {data.get('message', data)}")
    return data

def get_sesskey():
    """
    Ouvre une session admin et récupère son sesskey.

    Le logintoken doit être lu DANS la session qui postera le formulaire :
    Moodle le lie à la session, et un jeton obtenu hors session produit une
    connexion silencieusement anonyme — le sesskey renvoyé est alors celui d'un
    visiteur, et toute création ultérieure échoue sans message clair.
    """
    s = requests.Session()
    r = s.get(f"{MOODLE_URL}/login/index.php", timeout=30)
    m = re.search(r'name="logintoken" value="([^"]+)"', r.text)
    s.post(f"{MOODLE_URL}/login/index.php", data={
        "username": MOODLE_USER, "password": MOODLE_PASS,
        "logintoken": m.group(1) if m else ""
    }, timeout=30, allow_redirects=True)
    r2 = s.get(f"{MOODLE_URL}/", timeout=30)
    if "logout" not in r2.text.lower():
        raise RuntimeError(
            "Connexion admin à Moodle échouée : vérifier MOODLE_ADMIN_USER / "
            "MOODLE_ADMIN_PASSWORD dans .env")
    m2 = re.search(r'"sesskey":"([^"]+)"', r2.text)
    return s, m2.group(1) if m2 else ""

def create_course(shortname, fullname, category=1):
    """Idempotent : réutilise le cours si son shortname existe déjà."""
    existing = api("core_course_get_courses", {})
    if isinstance(existing, list):
        for c in existing:
            if c.get("shortname") == shortname:
                return c["id"]
    data = api("core_course_create_courses", {
        "courses[0][fullname]":  fullname,
        "courses[0][shortname]": shortname,
        "courses[0][categoryid]": category,
        "courses[0][format]":    "topics",
    }, "POST")
    return data[0]["id"]

def enrol_user(userid, courseid, roleid=5):
    api("enrol_manual_enrol_users", {
        "enrolments[0][roleid]":   roleid,
        "enrolments[0][userid]":   userid,
        "enrolments[0][courseid]": courseid,
    }, "POST")


def service_user_id():
    """Identifiant de l'utilisateur rattaché au jeton de service web."""
    return api("core_webservice_get_site_info", {}).get("userid")


def enrol_service_user(courseid):
    """
    Inscrit l'utilisateur du jeton comme enseignant dans le cours.

    Sans cette inscription, mod_assign_get_submissions et
    mod_assign_get_assignments répondent « User is not enrolled or does not
    have requested capability » : les devoirs existent mais restent invisibles
    au scheduler, qui n'évalue alors rien du tout.
    """
    uid = service_user_id()
    if uid:
        enrol_user(uid, courseid, roleid=3)   # 3 = enseignant éditeur
    return uid

def find_user(username):
    """Retourne l'id d'un utilisateur existant, ou None."""
    data = api("core_user_get_users", {
        "criteria[0][key]":   "username",
        "criteria[0][value]": username,
    })
    users = data.get("users", []) if isinstance(data, dict) else []
    return users[0]["id"] if users else None


def create_user(username, firstname, lastname, password=None):
    """Idempotent : réutilise le compte s'il existe, pour que le seed soit rejouable."""
    existing = find_user(username)
    if existing:
        return existing
    if not password:
        password = firstname + "1234!"
    data = api("core_user_create_users", {
        "users[0][username]":  username,
        "users[0][password]":  password,
        "users[0][firstname]": firstname,
        "users[0][lastname]":  lastname,
        "users[0][email]":     f"{username}@eachs.test",
    }, "POST")
    return data[0]["id"]

def find_assign(courseid, name):
    """Retourne l'id d'un devoir portant ce nom dans le cours, ou None."""
    data = api("mod_assign_get_assignments", {"courseids[0]": courseid})
    for c in data.get("courses", []):
        for a in c.get("assignments", []):
            if a["name"] == name:
                return a["id"]
    return None


def create_assign(courseid, name, description, grade=100):
    """Idempotent : ne recrée pas un devoir déjà présent sous le même nom."""
    existing = find_assign(courseid, name)
    if existing:
        return existing
    sess, sesskey = get_sesskey()
    payload = {
        "sesskey": sesskey,
        "mform_isexpanded_id_general": "1",
        "mform_isexpanded_id_availability": "0",
        "mform_isexpanded_id_submissionsettings": "1",
        "mform_isexpanded_id_groupsubmissionsettings": "0",
        "mform_isexpanded_id_notifications": "0",
        "mform_isexpanded_id_grade": "1",
        "mform_isexpanded_id_modstandardelshdr": "1",
        "mform_isexpanded_id_modstandardelshdr_adv": "0",
        "mform_isexpanded_id_activitycompletionhdr": "0",
        "mform_isexpanded_id_tagshdr": "0",
        "id": "0",
        "course": courseid,
        "coursemodule": "0",
        "section": "1",
        "module": "1",
        "modulename": "assign",
        "instance": "0",
        "add": "assign",
        "update": "0",
        "return": "0",
        "sr": "0",
        "name": name,
        "introeditor[text]": description,
        "introeditor[format]": "1",
        "introeditor[itemid]": "0",
        "showdescription": "0",
        "duedate[enabled]": "0",
        "cutoffdate[enabled]": "0",
        "gradingduedate[enabled]": "0",
        "alwaysshowdescription": "1",
        "submissiondrafts": "0",
        "requiresubmissionstatement": "0",
        "sendnotifications": "0",
        "sendlatenotifications": "0",
        "sendstudentnotifications": "1",
        "duedate[day]": "1",
        "duedate[month]": "1",
        "duedate[year]": "2030",
        "duedate[hour]": "0",
        "duedate[minute]": "0",
        "cutoffdate[day]": "1",
        "cutoffdate[month]": "1",
        "cutoffdate[year]": "2030",
        "cutoffdate[hour]": "0",
        "cutoffdate[minute]": "0",
        "gradingduedate[day]": "1",
        "gradingduedate[month]": "1",
        "gradingduedate[year]": "2030",
        "gradingduedate[hour]": "0",
        "gradingduedate[minute]": "0",
        "teamsubmission": "0",
        "requireallteammemberssubmit": "0",
        "teamsubmissiongroupingid": "0",
        "blindmarking": "0",
        "hidegrader": "0",
        "attemptreopenmethod": "none",
        "maxattempts": "-1",
        "markingworkflow": "0",
        "markingallocation": "0",
        "grade[modgrade_type]": "point",
        "grade[modgrade_point]": str(grade),
        "grade[modgrade_scale]": "0",
        "completionunlocked": "1",
        "completion": "1",
        "completionview": "0",
        "completiongradeitemnumber": "",
        "completionpassgrade": "0",
        "completionusegrade": "0",
        "completionexpected[enabled]": "0",
        "tags": "",
        "availabilityconditionsjson": '{"op":"&","c":[],"showc":[]}',
        "activityeditor[text]": "",
        "activityeditor[format]": "1",
        "activityeditor[itemid]": "0",
        "_qf__mod_assign_mod_form": "1",
        "submitbutton2": "Save and return to course",
        "assignsubmission_onlinetext_enabled": "1",
        "assignsubmission_file_enabled": "1",
        "assignsubmission_file_maxfiles": "1",
        "assignsubmission_file_maxsizebytes": "0",
        "assignfeedback_comments_enabled": "1",
        "assignfeedback_editpdf_enabled": "0",
        "assignfeedback_file_enabled": "0",
    }
    r = sess.post(
        f"{MOODLE_URL}/course/modedit.php",
        data=payload, timeout=30
    )
    # Trouver l'ID du devoir créé
    r2 = api("mod_assign_get_assignments", {
        "courseids[0]": courseid
    })
    for c in r2.get("courses", []):
        for a in c.get("assignments", []):
            if a["name"] == name:
                return a["id"]
    return None

def submit_text(assignment_id, user_id, text, password):
    """
    Soumet un texte en ligne en tant qu'étudiant.

    Les champs cachés du formulaire sont relus sur la page plutôt que codés en
    dur : Moodle en attend plusieurs qui varient selon la version et la
    configuration du devoir (lastmodified, userid, itemid du filemanager…), et
    un seul manquant fait échouer l'enregistrement silencieusement, en laissant
    une soumission vide au statut « new » que le scheduler ignore ensuite.

    Retourne True si le texte est bien enregistré.
    """
    cmid = _assign_cmid.get(assignment_id, 0)
    username = _user_map.get(user_id, {}).get("username", "")
    s = requests.Session()

    r0 = s.get(f"{MOODLE_URL}/login/index.php", timeout=30)
    m = re.search(r'name="logintoken" value="([^"]+)"', r0.text)
    s.post(f"{MOODLE_URL}/login/index.php", data={
        "username": username,
        "password": password,
        "logintoken": m.group(1) if m else "",
    }, timeout=30, allow_redirects=True)

    r1 = s.get(f"{MOODLE_URL}/mod/assign/view.php?id={cmid}&action=editsubmission",
               timeout=30)
    if "_qf__mod_assign_submission_form" not in r1.text:
        print(f"    ✗ formulaire de soumission inaccessible (user={user_id}, cm={cmid})")
        return False

    # Tous les champs cachés du formulaire, tels que Moodle les fournit.
    payload = {}
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', r1.text):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            payload[name.group(1)] = value.group(1) if value else ""

    # Le libellé du bouton dépend de la langue de l'interface Moodle et fait
    # partie des données validées : on le relit au lieu de le coder en dur.
    label = "Save changes"
    for tag in re.findall(r'<input[^>]*type="submit"[^>]*>', r1.text):
        if 'name="submitbutton"' in tag:
            value = re.search(r'value="([^"]*)"', tag)
            if value:
                label = value.group(1)
            break

    payload.update({
        "onlinetext_editor[text]": text,
        "submitbutton": label,
    })
    s.post(f"{MOODLE_URL}/mod/assign/view.php", data=payload, timeout=30,
           allow_redirects=True)

    # Vérification : une soumission enregistree n'est plus au statut "new".
    check = api("mod_assign_get_submissions", {"assignmentids[0]": assignment_id})
    for a in check.get("assignments", []):
        for sub in a.get("submissions", []):
            if sub.get("userid") == user_id:
                status = sub.get("status")
                if status == "submitted":
                    print(f"    → Soumission enregistree : user={user_id} ({status})")
                    return True
                print(f"    ✗ Soumission non prise en compte : user={user_id} (statut={status})")
                return False
    print(f"    ✗ Soumission introuvable : user={user_id}")
    return False

# maps globaux remplis au fur et à mesure
_user_map    = {}   # user_id -> {username, password}
_assign_cmid = {}   # assign_id -> coursemodule_id

def get_cmid(assign_id, course_id):
    """Récupère le course module ID d'un devoir."""
    r = api("core_course_get_contents", {"courseid": course_id})
    for section in r:
        for mod in section.get("modules", []):
            if mod.get("modname") == "assign" and mod.get("instance") == assign_id:
                return mod["id"]
    return 0

# ── données de seed ───────────────────────────────────────────────────────────

# Suffixe ajouté aux shortnames de cours. Moodle impose des shortnames uniques :
# sur une instance qui porte déjà des campagnes antérieures, un suffixe (par
# exemple l'année universitaire) crée un jeu de cours neuf sans rien supprimer.
# Reporter la même valeur dans EACHS_COURSES (.env) pour que le scheduler
# n'évalue que ces cours.
COURSE_SUFFIX = os.environ.get("SEED_COURSE_SUFFIX", "")

COURSES = [
    {"shortname": "IA-M2",  "fullname": "M2 Intelligence Artificielle"},
    {"shortname": "GL-L3",  "fullname": "L3 Génie Logiciel"},
    {"shortname": "BDA-M1", "fullname": "M1 Bases de Données Avancées"},
    {"shortname": "ALGO-L2","fullname": "L2 Algorithmique"},
]

# 4 devoirs par type = 16 devoirs au total, 4 cours x 4 devoirs
# task_type est encodé dans la formulation de la question pour detect_task_type()
ASSIGNMENTS = [
    # ── Cours IA-M2 ──────────────────────────────────────────────────────────
    {
        "course": "IA-M2",
        "name": "QCM — Fondamentaux du Machine Learning",
        "desc": "Parmi les propositions suivantes, laquelle définit correctement l'apprentissage supervisé ? A) Le modèle apprend sans données étiquetées. B) Le modèle apprend à partir de paires entrée-sortie étiquetées. C) Le modèle apprend par renforcement uniquement. D) Le modèle copie les données d'entraînement.",
        "grade": 20,
    },
    {
        "course": "IA-M2",
        "name": "Définition courte — Overfitting",
        "desc": "En deux phrases maximum, définissez le surapprentissage (overfitting) et citez une technique pour l'éviter.",
        "grade": 10,
    },
    {
        "course": "IA-M2",
        "name": "Dissertation — Enjeux de l'IA générative",
        "desc": "Expliquez en quoi l'IA générative transforme les pratiques professionnelles. Présentez deux opportunités et deux risques concrets, en vous appuyant sur des exemples issus de secteurs différents.",
        "grade": 100,
    },
    {
        "course": "IA-M2",
        "name": "Exercice formel — Calcul de gradient",
        "desc": "Calculez le gradient de la fonction de coût L(w) = (y - wx)² par rapport à w. Montrez toutes les étapes du calcul et précisez la règle de dérivation utilisée.",
        "grade": 20,
    },
    # ── Cours GL-L3 ──────────────────────────────────────────────────────────
    {
        "course": "GL-L3",
        "name": "QCM — Patrons de conception",
        "desc": "Quel patron de conception garantit qu'une classe n'a qu'une seule instance ? A) Factory B) Observer C) Singleton D) Strategy. Choisissez la bonne réponse et justifiez en une phrase.",
        "grade": 10,
    },
    {
        "course": "GL-L3",
        "name": "Réponse courte — SOLID",
        "desc": "Décrivez en une ou deux phrases le principe de responsabilité unique (SRP) du modèle SOLID. Donnez un exemple concret.",
        "grade": 10,
    },
    {
        "course": "GL-L3",
        "name": "Analyse — Tests logiciels",
        "desc": "Comparez les approches TDD (Test-Driven Development) et BDD (Behavior-Driven Development). Analysez leurs avantages et inconvénients respectifs dans un projet agile. Justifiez vos arguments avec des exemples concrets.",
        "grade": 100,
    },
    {
        "course": "GL-L3",
        "name": "Démonstration — Complexité algorithmique",
        "desc": "Démontrez que la complexité temporelle du tri par insertion est O(n²) dans le pire des cas. Utilisez une preuve formelle par récurrence ou par analyse du nombre de comparaisons.",
        "grade": 20,
    },
    # ── Cours BDA-M1 ─────────────────────────────────────────────────────────
    {
        "course": "BDA-M1",
        "name": "QCM — Propriétés ACID",
        "desc": "Parmi les propositions suivantes, quelle propriété ACID garantit qu'une transaction est exécutée en totalité ou pas du tout ? A) Atomicité B) Cohérence C) Isolation D) Durabilité.",
        "grade": 10,
    },
    {
        "course": "BDA-M1",
        "name": "Définition — Normalisation",
        "desc": "Définissez en deux phrases la troisième forme normale (3NF) et expliquez pourquoi elle est importante dans la conception d'une base de données relationnelle.",
        "grade": 10,
    },
    {
        "course": "BDA-M1",
        "name": "Étude de cas — Optimisation SQL",
        "desc": "Rédigez une analyse comparative des stratégies d'indexation dans PostgreSQL. Discutez des index B-tree, Hash et GIN en précisant dans quels contextes chacun est le plus adapté. Appuyez-vous sur des exemples de requêtes.",
        "grade": 100,
    },
    {
        "course": "BDA-M1",
        "name": "Preuve formelle — Dépendances fonctionnelles",
        "desc": "Prouvez que si X → Y et Y → Z, alors X → Z (transitivité des dépendances fonctionnelles). Utilisez la définition formelle des dépendances fonctionnelles et les axiomes d'Armstrong.",
        "grade": 20,
    },
    # ── Cours ALGO-L2 ────────────────────────────────────────────────────────
    {
        "course": "ALGO-L2",
        "name": "QCM — Complexité de BFS",
        "desc": "Quelle est la complexité temporelle de l'algorithme BFS (parcours en largeur) sur un graphe avec V sommets et E arêtes ? A) O(V) B) O(E) C) O(V+E) D) O(V*E). Justifiez votre choix.",
        "grade": 10,
    },
    {
        "course": "ALGO-L2",
        "name": "Réponse courte — Récursivité",
        "desc": "Expliquez en deux phrases le principe de la récursivité. Donnez la condition d'arrêt de la fonction factorielle récursive.",
        "grade": 10,
    },
    {
        "course": "ALGO-L2",
        "name": "Dissertation — Tri et recherche",
        "desc": "Comparez les algorithmes de tri rapide (quicksort) et de tri fusion (mergesort). Analysez leur complexité temporelle dans le meilleur cas, le pire cas et le cas moyen. Discutez leurs avantages pratiques et cas d'usage.",
        "grade": 100,
    },
    {
        "course": "ALGO-L2",
        "name": "Résolution formelle — Dijkstra",
        "desc": "Résolvez le problème du plus court chemin avec l'algorithme de Dijkstra sur le graphe suivant : S→A(4), S→B(2), A→C(3), B→A(1), B→C(5), C→D(2). Montrez toutes les étapes de l'algorithme et donnez le chemin optimal de S à D.",
        "grade": 20,
    },
]

# 4 profils étudiants × 4 cours = bien distribués
STUDENTS = [
    {"username": "alice_martin",   "firstname": "Alice",   "lastname": "Martin",   "password": "Alice1234!"},
    {"username": "bob_dupont",     "firstname": "Bob",     "lastname": "Dupont",   "password": "Bob1234!"},
    {"username": "clara_rousseau", "firstname": "Clara",   "lastname": "Rousseau", "password": "Clara1234!"},
    {"username": "david_petit",    "firstname": "David",   "lastname": "Petit",    "password": "David1234!"},
]

# Réponses par profil et par type de tâche
RESPONSES = {
    "QCM — Fondamentaux du Machine Learning": {
        "alice_martin":   "B) Le modèle apprend à partir de paires entrée-sortie étiquetées. En apprentissage supervisé, chaque exemple d'entraînement est associé à une étiquette (label) qui indique la sortie attendue.",
        "bob_dupont":     "B) Le modèle apprend à partir de données étiquetées.",
        "clara_rousseau": "A) Le modèle apprend sans données étiquetées.",
        "david_petit":    "C) Le modèle apprend par renforcement uniquement.",
    },
    "Définition courte — Overfitting": {
        "alice_martin":   "Le surapprentissage survient quand un modèle mémorise les données d'entraînement au lieu d'apprendre les patterns généraux. Pour l'éviter, on peut utiliser la régularisation L2, le dropout, ou la validation croisée.",
        "bob_dupont":     "L'overfitting c'est quand le modèle est trop bien adapté aux données d'entraînement et généralise mal. On peut l'éviter avec plus de données ou la régularisation.",
        "clara_rousseau": "C'est quand le modèle apprend trop bien les données. On utilise plus de données.",
        "david_petit":    "L'overfitting est un problème de machine learning.",
    },
    "Dissertation — Enjeux de l'IA générative": {
        "alice_martin":   "L'IA générative transforme profondément les pratiques professionnelles en automatisant des tâches créatives et analytiques. Dans le secteur médical, des modèles comme Med-PaLM 2 assistent les diagnostics en analysant des millions de cas cliniques. Dans le domaine juridique, des outils comme Harvey AI rédigent des contrats en quelques secondes. Ces opportunités s'accompagnent cependant de risques majeurs : les hallucinations des modèles peuvent induire des erreurs critiques dans des contextes à fort enjeu, et la concentration des capacités IA chez quelques acteurs crée des déséquilibres concurrentiels préoccupants.",
        "bob_dupont":     "L'IA générative change beaucoup de métiers. Dans le journalisme, des outils génèrent automatiquement des articles. Dans le design, Midjourney crée des visuels professionnels. Mais il y a des risques comme les deepfakes qui peuvent tromper les gens, et la perte d'emplois dans certains secteurs créatifs.",
        "clara_rousseau": "L'IA générative est utilisée dans beaucoup de domaines. Elle peut créer du texte et des images. C'est utile pour les entreprises mais il y a aussi des problèmes éthiques.",
        "david_petit":    "L'IA générative fait des choses automatiquement. C'est bien pour le travail.",
    },
    "Exercice formel — Calcul de gradient": {
        "alice_martin":   "L(w) = (y - wx)². En appliquant la règle de dérivation en chaîne : dL/dw = 2(y - wx) × d(y - wx)/dw = 2(y - wx) × (-x) = -2x(y - wx). Le gradient vaut donc ∇wL = -2x(y - wx), ce qui permet la mise à jour w ← w - α × (-2x(y - wx)) en descente de gradient.",
        "bob_dupont":     "On dérive L(w) = (y - wx)² par rapport à w. En utilisant la règle de la chaîne : dL/dw = 2(y - wx) × (-x) = -2x(y - wx).",
        "clara_rousseau": "La dérivée de (y - wx)² est 2(y - wx). On multiplie par -x car on dérive par rapport à w.",
        "david_petit":    "Je ne sais pas calculer ce gradient.",
    },
    "QCM — Patrons de conception": {
        "alice_martin":   "C) Singleton. Ce patron garantit qu'une classe n'a qu'une seule instance en rendant le constructeur privé et en exposant une méthode statique getInstance() qui crée l'instance si elle n'existe pas encore.",
        "bob_dupont":     "C) Singleton. Il assure une seule instance avec un constructeur privé.",
        "clara_rousseau": "B) Observer.",
        "david_petit":    "A) Factory.",
    },
    "Réponse courte — SOLID": {
        "alice_martin":   "Le principe de responsabilité unique (SRP) stipule qu'une classe ne doit avoir qu'une seule raison de changer, c'est-à-dire une seule responsabilité métier. Exemple : une classe UserService gère uniquement la logique utilisateur, tandis qu'une classe UserRepository s'occupe exclusivement de la persistance.",
        "bob_dupont":     "SRP signifie qu'une classe doit faire une seule chose. Par exemple, une classe pour gérer les utilisateurs ne doit pas aussi gérer l'envoi d'emails.",
        "clara_rousseau": "C'est le principe qui dit qu'une classe doit avoir une seule responsabilité.",
        "david_petit":    "SRP est un principe de programmation.",
    },
    "Analyse — Tests logiciels": {
        "alice_martin":   "TDD (Test-Driven Development) consiste à écrire les tests avant le code de production, suivant le cycle rouge-vert-refactoring. BDD (Behavior-Driven Development) étend cette approche en formulant les tests en langage naturel (Given-When-Then) pour favoriser la collaboration entre développeurs et parties prenantes. TDD est optimal pour les équipes techniques soucieuses de la couverture de code, tandis que BDD est précieux dans les projets où la communication métier est critique. Dans un projet agile, les deux approches sont complémentaires : BDD pour les critères d'acceptation, TDD pour l'implémentation technique.",
        "bob_dupont":     "TDD consiste à écrire d'abord les tests puis le code. BDD se concentre sur le comportement attendu du système en langage naturel. TDD est plus technique, BDD est plus orienté métier. Les deux s'utilisent bien en agile car ils favorisent la qualité du code.",
        "clara_rousseau": "TDD c'est écrire les tests avant le code. BDD c'est définir le comportement voulu. TDD est utile pour les développeurs et BDD pour communiquer avec les clients.",
        "david_petit":    "TDD et BDD sont des méthodes de test. TDD écrit les tests avant. BDD aussi.",
    },
    "Démonstration — Complexité algorithmique": {
        "alice_martin":   "Le tri par insertion parcourt le tableau de gauche à droite. Pour chaque élément i, il le compare avec les éléments précédents jusqu'à trouver sa position. Dans le pire cas (tableau trié en ordre décroissant), l'élément i doit être comparé avec tous les i-1 éléments précédents. Le nombre total de comparaisons est donc : somme de k pour k de 1 à n-1 = n(n-1)/2. Par définition de la notation O, n(n-1)/2 ∈ O(n²). CQFD.",
        "bob_dupont":     "Pour chaque élément i de 1 à n, on fait au maximum i comparaisons dans le pire cas. Total = 1+2+...+(n-1) = n(n-1)/2. C'est bien O(n²) car n(n-1)/2 ≤ n² pour tout n.",
        "clara_rousseau": "Le tri par insertion compare chaque élément avec les précédents. Dans le pire cas on fait beaucoup de comparaisons, donc c'est O(n²).",
        "david_petit":    "C'est O(n²) parce que c'est un tri.",
    },
    "QCM — Propriétés ACID": {
        "alice_martin":   "A) Atomicité. Cette propriété garantit que toutes les opérations d'une transaction sont exécutées intégralement ou qu'aucune ne l'est (tout ou rien), ce qui prévient les états incohérents en cas de défaillance.",
        "bob_dupont":     "A) Atomicité. Elle garantit que la transaction est soit complète soit annulée.",
        "clara_rousseau": "B) Cohérence.",
        "david_petit":    "D) Durabilité.",
    },
    "Définition — Normalisation": {
        "alice_martin":   "La 3NF exige que toutes les dépendances fonctionnelles non-triviales aient pour déterminant une clé candidate ou un superclé, éliminant ainsi les dépendances transitives. Elle est importante car elle réduit la redondance des données et prévient les anomalies d'insertion, de mise à jour et de suppression.",
        "bob_dupont":     "La 3NF signifie qu'un attribut non-clé ne doit dépendre que de la clé primaire, pas d'un autre attribut non-clé. Cela évite la redondance et les problèmes de mise à jour.",
        "clara_rousseau": "La 3NF est une règle de normalisation qui supprime les dépendances transitives pour réduire la redondance.",
        "david_petit":    "La normalisation c'est organiser les données dans une base de données.",
    },
    "Étude de cas — Optimisation SQL": {
        "alice_martin":   "L'indexation est cruciale pour les performances des bases de données relationnelles. L'index B-tree, structure par défaut de PostgreSQL, est optimal pour les requêtes d'égalité et de plage (WHERE age > 25 AND age < 40) grâce à sa structure arborescente équilibrée. L'index Hash offre des recherches en O(1) pour les équijoins (WHERE email = 'x@y.com') mais ne supporte pas les inégalités. L'index GIN (Generalized Inverted Index) excelle pour les recherches full-text et les tableaux (WHERE tags @> '{postgresql}'). Une stratégie hybride combinant B-tree sur les colonnes de filtrage fréquent et GIN sur les colonnes textuelles peut réduire le temps de requête de 95% sur de grandes tables.",
        "bob_dupont":     "PostgreSQL propose plusieurs types d'index. Le B-tree est le plus courant et convient pour les comparaisons et les tris. Le Hash est rapide pour les égalités exactes. Le GIN est utile pour la recherche full-text. Le choix dépend du type de requêtes : B-tree pour la plupart des cas, GIN pour les textes et tableaux.",
        "clara_rousseau": "Les index améliorent les performances SQL. B-tree est pour les comparaisons, Hash pour les égalités, GIN pour les textes. Il faut choisir selon les requêtes.",
        "david_petit":    "Les index sont utiles pour accélérer les requêtes SQL.",
    },
    "Preuve formelle — Dépendances fonctionnelles": {
        "alice_martin":   "Soit X → Y et Y → Z. Par définition, X → Y signifie que pour toute paire de tuples t1, t2 tels que t1[X] = t2[X], on a t1[Y] = t2[Y]. De même, Y → Z signifie que si t1[Y] = t2[Y] alors t1[Z] = t2[Z]. Prenons deux tuples t1, t2 tels que t1[X] = t2[X]. Par X → Y, t1[Y] = t2[Y]. Par Y → Z, t1[Z] = t2[Z]. Donc pour tout t1, t2 vérifiant t1[X] = t2[X], on a t1[Z] = t2[Z], ce qui est exactement la définition de X → Z. CQFD.",
        "bob_dupont":     "Si X → Y, alors deux tuples identiques sur X sont identiques sur Y. Si Y → Z, alors deux tuples identiques sur Y sont identiques sur Z. Donc si deux tuples sont identiques sur X, ils sont identiques sur Y, donc sur Z. D'où X → Z.",
        "clara_rousseau": "Si X détermine Y et Y détermine Z, alors X détermine Z par transitivité. C'est comme en algèbre.",
        "david_petit":    "X → Z parce que X → Y → Z.",
    },
    "QCM — Complexité de BFS": {
        "alice_martin":   "C) O(V+E). BFS utilise une file FIFO : chaque sommet est enfilé et défilé exactement une fois (V opérations), et pour chaque sommet on parcourt toutes ses arêtes adjacentes (E opérations au total). La complexité est donc O(V+E).",
        "bob_dupont":     "C) O(V+E) car on visite chaque sommet et chaque arête une fois.",
        "clara_rousseau": "B) O(E).",
        "david_petit":    "A) O(V).",
    },
    "Réponse courte — Récursivité": {
        "alice_martin":   "La récursivité est une technique où une fonction s'appelle elle-même pour résoudre un sous-problème de taille réduite. Pour la factorielle, la condition d'arrêt est n = 0 (ou n = 1), qui retourne 1 sans appel récursif supplémentaire.",
        "bob_dupont":     "Une fonction récursive s'appelle elle-même. Pour la factorielle, on s'arrête quand n vaut 0 et on retourne 1.",
        "clara_rousseau": "La récursivité c'est quand une fonction se rappelle. La factorielle s'arrête à 0.",
        "david_petit":    "C'est une fonction qui se rappelle.",
    },
    "Dissertation — Tri et recherche": {
        "alice_martin":   "Le tri rapide (quicksort) et le tri fusion (mergesort) sont deux algorithmes de tri par comparaison aux comportements complémentaires. Quicksort, basé sur le partitionnement autour d'un pivot, atteint O(n log n) en moyenne mais dégénère en O(n²) dans le pire cas (pivot mal choisi sur tableau déjà trié). Mergesort garantit O(n log n) dans tous les cas grâce à sa stratégie diviser-pour-régner équilibrée, au prix d'une complexité spatiale O(n). En pratique, quicksort est préféré pour les tableaux en mémoire grâce à sa meilleure localité de cache, tandis que mergesort est adapté au tri externe (données sur disque) et est stable, préservant l'ordre relatif des éléments égaux.",
        "bob_dupont":     "Quicksort est en O(n log n) en moyenne et O(n²) au pire. Mergesort est toujours en O(n log n) mais utilise O(n) en mémoire. Quicksort est plus rapide en pratique pour les petits tableaux, mergesort est mieux pour les grands ensembles et les tris stables.",
        "clara_rousseau": "Quicksort est rapide mais peut être lent dans certains cas. Mergesort est toujours en O(n log n). On choisit selon le contexte.",
        "david_petit":    "Quicksort et mergesort sont deux algorithmes de tri. Ils sont tous les deux bons.",
    },
    "Résolution formelle — Dijkstra": {
        "alice_martin":   "Initialisation : dist = {S:0, A:∞, B:∞, C:∞, D:∞}\nÉtape 1 : u=S, relax S→A : dist[A]=4, relax S→B : dist[B]=2. File : {A:4, B:2, C:∞, D:∞}\nÉtape 2 : u=B (dist=2), relax B→A : dist[A]=min(4,3)=3, relax B→C : dist[C]=7. File : {A:3, C:7, D:∞}\nÉtape 3 : u=A (dist=3), relax A→C : dist[C]=min(7,6)=6. File : {C:6, D:∞}\nÉtape 4 : u=C (dist=6), relax C→D : dist[D]=8. File : {D:8}\nÉtape 5 : u=D (dist=8). Terminé.\nChemin optimal S→D : S→B→A→C→D, distance = 8.",
        "bob_dupont":     "On part de S avec dist[S]=0. On relaxe les voisins : B(2) et A(4). On prend B, on met à jour A(3) et C(7). On prend A(3), C devient 6. On prend C(6), D devient 8. Plus court chemin vers D = 8 via S-B-A-C-D.",
        "clara_rousseau": "Dijkstra depuis S : on trouve le chemin le plus court vers D qui est 8.",
        "david_petit":    "Je ne suis pas sûr mais le plus court chemin est S→A→D.",
    },
}

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("SEED DEMO — Répartition équilibrée 4 types de tâches")
    print("=" * 60)

    # 1. Créer les cours
    print("\n[1/4] Création des cours...")
    course_ids = {}
    for c in COURSES:
        # La clé reste le shortname court : les 16 devoirs y font référence.
        shortname = c["shortname"] + COURSE_SUFFIX
        cid = create_course(shortname, c["fullname"])
        course_ids[c["shortname"]] = cid
        uid = enrol_service_user(cid)
        print(f"  ✓ {shortname} → id={cid} (utilisateur de service {uid} inscrit comme enseignant)")

    # 2. Créer les étudiants
    print("\n[2/4] Création des étudiants...")
    student_ids = {}
    for s in STUDENTS:
        uid = create_user(s["username"], s["firstname"], s["lastname"], s["password"])
        student_ids[s["username"]] = uid
        _user_map[uid] = {"username": s["username"], "password": s["password"]}
        print(f"  ✓ {s['firstname']} {s['lastname']} → id={uid}")

    # 3. Inscrire les étudiants dans tous les cours
    print("\n[3/4] Inscription des étudiants...")
    for cshort, cid in course_ids.items():
        for sname, uid in student_ids.items():
            enrol_user(uid, cid)
        print(f"  ✓ {cshort} — {len(student_ids)} étudiants inscrits")

    # 4. Créer les devoirs et les soumissions
    print("\n[4/4] Création des devoirs et soumissions...")
    assign_map = {}
    for a in ASSIGNMENTS:
        cshort = a["course"]
        cid    = course_ids[cshort]
        aid    = create_assign(cid, a["name"], a["desc"], a.get("grade", 100))
        if not aid:
            print(f"  ✗ Impossible de créer : {a['name']}")
            continue
        assign_map[a["name"]] = aid
        cmid = get_cmid(aid, cid)
        _assign_cmid[aid] = cmid
        print(f"  ✓ [{cshort}] {a['name']} → assign_id={aid} cm_id={cmid}")

        # Soumissions
        responses = RESPONSES.get(a["name"], {})
        for s in STUDENTS:
            uname = s["username"]
            uid   = student_ids[uname]
            text  = responses.get(uname, "")
            if text:
                submit_text(aid, uid, text, s["password"])
                time.sleep(1)  # éviter le flood
            else:
                print(f"    → Pas de réponse pour {uname}")

    print("\n" + "=" * 60)
    print("SEED TERMINÉ")
    print(f"  Cours    : {len(course_ids)}")
    print(f"  Étudiants: {len(student_ids)}")
    print(f"  Devoirs  : {len(assign_map)}")
    print("\nRépartition des types :")
    print("  QCM             : 4 devoirs (25%)")
    print("  Réponse courte  : 4 devoirs (25%)")
    print("  Rédaction       : 4 devoirs (25%)")
    print("  Formel          : 4 devoirs (25%)")
    print("\nLancer le scheduler pour évaluer les soumissions :")
    print("  python scheduler.py")
    print("=" * 60)

if __name__ == "__main__":
    main()