"""
seed_complete.py — Crée cours, devoirs et soumissions en une seule commande.
Moodle 4.0.5
Lance avec : python3 seed_complete.py
"""
import os
import re
import requests
import time
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL = os.environ.get("MOODLE_URL", "http://localhost:8080")
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN")
ADMIN_USER = os.environ.get("MOODLE_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("MOODLE_ADMIN_PASSWORD", "Admin1234!")

DATA = [
    {
        "fullname": "Intelligence Artificielle — M2 MIAGE",
        "shortname": "IA-M2",
        "devoirs": [
            {
                "name": "Devoir 1 — Algorithmes de recherche",
                "description": "Expliquez la différence entre la recherche en largeur (BFS) et la recherche en profondeur (DFS). Dans quels cas privilégiez-vous l'une ou l'autre ?",
                "soumission": "BFS explore niveau par niveau en utilisant une file. Elle garantit le chemin le plus court dans un graphe non pondéré. DFS utilise une pile et explore en profondeur avant de revenir en arrière. On utilise BFS quand on cherche le plus court chemin et DFS quand on explore toutes les solutions possibles comme dans un labyrinthe.",
            },
            {
                "name": "Devoir 2 — Réseaux de neurones",
                "description": "Qu'est-ce que la rétropropagation du gradient ? Expliquez son rôle dans l'entraînement d'un réseau de neurones.",
                "soumission": "La rétropropagation calcule le gradient de la fonction de perte par rapport aux poids du réseau en utilisant la règle de la chaîne. Elle propage l'erreur depuis la couche de sortie vers les couches d'entrée pour mettre à jour les poids et réduire l'erreur.",
            },
            {
                "name": "Examen — Overfitting et régularisation",
                "description": "Qu'est-ce que le surapprentissage (overfitting) ? Expliquez ses causes et proposez deux méthodes pour l'éviter.",
                "soumission": "Le overfitting survient quand un modèle mémorise les données d'entraînement sans généraliser. Causes : modèle trop complexe, données insuffisantes. Solutions : régularisation L1/L2 qui pénalise les grands poids, et dropout qui désactive aléatoirement des neurones pendant l'entraînement.",
            },
        ]
    },
    {
        "fullname": "Bases de Données Avancées — M2",
        "shortname": "BDA-M2",
        "devoirs": [
            {
                "name": "Examen — Transactions et ACID",
                "description": "Définissez les quatre propriétés ACID d'une transaction de base de données. Donnez un exemple concret pour chaque propriété.",
                "soumission": "Atomicité : une transaction s'exécute entièrement ou pas du tout. Exemple : virement bancaire. Cohérence : la base reste dans un état valide. Isolation : les transactions concurrentes ne se voient pas. Durabilité : une fois validée, la transaction persiste même en cas de panne.",
            },
            {
                "name": "TP — Optimisation des requêtes",
                "description": "Expliquez ce qu'est un index en base de données, comment il améliore les performances et quels sont ses inconvénients.",
                "soumission": "Un index est une structure qui accélère les recherches en créant un raccourci vers les lignes d'une table. Il améliore les SELECT mais ralentit INSERT, UPDATE et DELETE car il doit être mis à jour. Il consomme aussi de l'espace disque supplémentaire.",
            },
            {
                "name": "Devoir — Modélisation UML",
                "description": "Expliquez la différence entre un diagramme de classes et un diagramme de séquence en UML. Quand utilise-t-on chacun ?",
                "soumission": "Le diagramme de classes représente la structure statique du système : les classes, leurs attributs et leurs relations. Le diagramme de séquence représente les interactions dynamiques entre objets dans le temps. On utilise le diagramme de classes pour concevoir la structure et le diagramme de séquence pour modéliser un scénario d'utilisation.",
            },
        ]
    },
    {
        "fullname": "Génie Logiciel — L3",
        "shortname": "GL-L3",
        "devoirs": [
            {
                "name": "Quiz — Patrons de conception",
                "description": "Décrivez le patron de conception Singleton. Expliquez son utilité et donnez un exemple d'utilisation.",
                "soumission": "Le Singleton garantit qu'une classe n'a qu'une seule instance et fournit un point d'accès global. On l'utilise pour gérer des ressources partagées comme une connexion à une base de données. Il s'implémente avec un constructeur privé et une méthode statique getInstance().",
            },
            {
                "name": "Devoir — Qualité du code",
                "description": "Qu'est-ce que la dette technique ? Expliquez ses causes, ses conséquences et comment la gérer dans un projet logiciel.",
                "soumission": "La dette technique désigne les compromis faits lors du développement qui rendent le code plus difficile à maintenir. Causes : pression temporelle, mauvaises pratiques. Conséquences : ralentissement du développement, accumulation de bugs. On la gère avec des revues de code régulières et du refactoring planifié.",
            },
            {
                "name": "Examen — Tests logiciels",
                "description": "Expliquez la différence entre les tests unitaires, les tests d'intégration et les tests end-to-end. Donnez un exemple pour chacun.",
                "soumission": "Les tests unitaires vérifient une fonction isolée, par exemple tester une fonction de calcul de TVA. Les tests d'intégration vérifient la collaboration entre plusieurs composants, comme tester l'interaction entre le service de paiement et la base de données. Les tests end-to-end simulent le parcours complet d'un utilisateur, comme tester le processus d'achat depuis la sélection jusqu'à la confirmation.",
            },
        ]
    },
]

# ─── API REST ────────────────────────────────────────────────────────
def api(function, params, method="GET"):
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    params.update({"wstoken": MOODLE_TOKEN, "wsfunction": function, "moodlewsrestformat": "json"})
    r = requests.post(url, data=params, timeout=30) if method == "POST" else requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    if not r.text.strip():
        return True  # Réponse vide = succès pour certaines fonctions Moodle
    result = r.json()
    if isinstance(result, dict) and "exception" in result:
        return None
    return result

# ─── Session web ─────────────────────────────────────────────────────

def get_session():
    session = requests.Session()
    r = session.get(f"{MOODLE_URL}/login/index.php", timeout=30)
    token_match = re.search(r'name="logintoken".*?value="([^"]+)"', r.text)
    logintoken = token_match.group(1) if token_match else ""
    session.post(f"{MOODLE_URL}/login/index.php", data={
        "username": ADMIN_USER, "password": ADMIN_PASS, "logintoken": logintoken
    }, allow_redirects=True, timeout=30)
    return session

# ─── Cours ───────────────────────────────────────────────────────────

def get_or_create_course(data):
    existing = api("core_course_get_courses", {})
    if existing:
        for c in existing:
            if c.get("shortname") == data["shortname"]:
                print(f"  Cours existant : [{c['id']}] {c['fullname']}")
                return c["id"]
    result = api("core_course_create_courses", {
        "courses[0][fullname]": data["fullname"],
        "courses[0][shortname]": data["shortname"],
        "courses[0][categoryid]": 1,
        "courses[0][format]": "topics",
    }, method="POST")
    if result and len(result) > 0:
        cid = result[0]["id"]
        print(f"  Cours créé : [{cid}] {data['fullname']}")
        return cid
    return None

# ─── Devoirs via session web ──────────────────────────────────────────

def create_assignment_web(session, course_id, devoir):
    # Charger le formulaire pour récupérer les champs cachés
    form_url = f"{MOODLE_URL}/course/modedit.php?add=assign&type=&course={course_id}&section=1&return=0&sr=0"
    r = session.get(form_url, timeout=30)

    hidden_fields = {}
    for match in re.finditer(r'<input[^>]+type=["\']hidden["\'][^>]*>', r.text, re.IGNORECASE):
        tag = match.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag)
        value_m = re.search(r'value=["\']([^"\']*)["\']', tag)
        if name_m:
            hidden_fields[name_m.group(1)] = value_m.group(1) if value_m else ""

    data = dict(hidden_fields)
    data.update({
        "name": devoir["name"],
        "introeditor[text]": devoir["description"],
        "introeditor[format]": "1",
        "introeditor[itemid]": hidden_fields.get("introeditor[itemid]", "0"),
        "activityeditor[text]": "",
        "activityeditor[format]": "1",
        "activityeditor[itemid]": hidden_fields.get("activityeditor[itemid]", "0"),
        "grade[modgrade_type]": "point",
        "grade[modgrade_point]": "100",
        "grade[modgrade_scale]": "",
        "gradepass": "",
        "gradecat": "0",
        "submissiondrafts": "0",
        "requiresubmissionstatement": "0",
        "sendnotifications": "0",
        "sendlatenotifications": "0",
        "sendstudentnotifications": "1",
        "assignsubmission_onlinetext_enabled": "1",
        "assignsubmission_file_enabled": "0",
        "assignsubmission_file_maxfiles": "20",
        "assignsubmission_file_maxsizebytes": "0",
        "assignfeedback_comments_enabled": "1",
        "assignfeedback_editpdf_enabled": "0",
        "assignfeedback_file_enabled": "0",
        "teamsubmission": "0",
        "requireallteammemberssubmit": "0",
        "teamsubmissiongroupingid": "0",
        "blindmarking": "0",
        "attemptreopenmethod": "none",
        "maxattempts": "-1",
        "availabilityconditionsjson": '{"op":"&","c":[],"showc":[]}',
        "submitbutton2": "Save and return to course",
    })

    r2 = session.post(f"{MOODLE_URL}/course/modedit.php", data=data, allow_redirects=True, timeout=30)
    time.sleep(1)

    if "modedit" in r2.url:
        fatal = re.findall(r'errormessage[^>]*>([^<]+)', r2.text)
        print(f"    Échec : {fatal[:1]}")
        return None

    # Vérifier que le devoir a été créé
    result = api("mod_assign_get_assignments", {"courseids[0]": course_id})
    if result:
        for c in result.get("courses", []):
            for a in c.get("assignments", []):
                if a["name"] == devoir["name"]:
                    print(f"    Devoir créé : [{a['id']}] {a['name']}")
                    return a["id"]
    return None

# ─── Soumissions ──────────────────────────────────────────────────────

def get_admin_id():
    result = api("core_user_get_users", {"criteria[0][key]": "username", "criteria[0][value]": "admin"})
    if result and result.get("users"):
        return result["users"][0]["id"]
    return None

def enroll_user(course_id, user_id):
    api("enrol_manual_enrol_users", {
        "enrolments[0][roleid]": 5,
        "enrolments[0][userid]": user_id,
        "enrolments[0][courseid]": course_id,
    }, method="POST")

def has_submission(assignment_id, user_id):
    result = api("mod_assign_get_submissions", {"assignmentids[0]": assignment_id})
    if result:
        for a in result.get("assignments", []):
            for s in a.get("submissions", []):
                if s.get("userid") == user_id and s.get("status") == "submitted":
                    return True
    return False

def submit(assignment_id, text):
    result = api("mod_assign_save_submission", {
        "assignmentid": assignment_id,
        "plugindata[onlinetext_editor][text]": text,
        "plugindata[onlinetext_editor][format]": 1,
        "plugindata[onlinetext_editor][itemid]": 0,
    }, method="POST")
    return result is not None

# ─── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Seed complet EACHS ===\n")

    session = get_session()
    admin_id = get_admin_id()
    if not admin_id:
        print("ERREUR : impossible de récupérer l'ID admin.")
        exit(1)
    print(f"Admin ID : {admin_id}\n")

    total_courses = total_devoirs = total_soumissions = 0

    for course_data in DATA:
        print(f"\n[COURS] {course_data['fullname']}")
        course_id = get_or_create_course(course_data)
        if not course_id:
            continue
        total_courses += 1
        enroll_user(course_id, admin_id)

        for devoir_data in course_data["devoirs"]:
            print(f"\n  [DEVOIR] {devoir_data['name']}")

            # Vérifier si le devoir existe déjà
            assignment_id = None
            existing = api("mod_assign_get_assignments", {"courseids[0]": course_id})
            if existing:
                for c in existing.get("courses", []):
                    for a in c.get("assignments", []):
                        if a["name"] == devoir_data["name"]:
                            print(f"    Existant : [{a['id']}]")
                            assignment_id = a["id"]

            if not assignment_id:
                assignment_id = create_assignment_web(session, course_id, devoir_data)
                if not assignment_id:
                    continue

            total_devoirs += 1

            if has_submission(assignment_id, admin_id):
                print(f"    Soumission existante, on passe.")
                continue

            print(f"    Soumission : {devoir_data['soumission'][:60]}...")
            ok = submit(assignment_id, devoir_data["soumission"])
            if ok:
                print(f"    ✓ Soumise")
                total_soumissions += 1
            else:
                print(f"    ✗ Échec soumission")
            time.sleep(0.5)

    print(f"\n=== Terminé ===")
    print(f"Cours : {total_courses} | Devoirs : {total_devoirs} | Soumissions : {total_soumissions}")
    print(f"\nLance ensuite : python3 scheduler.py")