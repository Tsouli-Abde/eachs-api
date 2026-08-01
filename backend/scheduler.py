import os
import re
import json
import requests
import logging
import ollama
import time
import tempfile
from datetime import datetime, timezone
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# Le suivi des soumissions déjà évaluées passe désormais par la base SQLite
# (backend/audit.py), plus par le fichier audit_log.json.
from audit import get_last_evaluation_time

load_dotenv()

MOODLE_URL = os.environ.get("MOODLE_URL", "http://localhost:8080")
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN")
MOODLE_ADMIN_USER = os.environ.get("MOODLE_ADMIN_USER", "admin")
MOODLE_ADMIN_PASSWORD = os.environ.get("MOODLE_ADMIN_PASSWORD", "Admin1234!")
EACHS_URL = os.environ.get("EACHS_URL", "http://localhost:8000")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 30))
AI_BACKEND = os.environ.get("AI_BACKEND", "local")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")

# Périmètre d'activation : liste de shortnames de cours séparés par des
# virgules. Vide = tous les cours. Déployer l'assistance sur une plateforme
# entière est rarement souhaitable : un établissement l'active cours par cours,
# après accord de l'équipe pédagogique. Ce filtre matérialise cette décision.
EACHS_COURSES = [c.strip() for c in os.environ.get("EACHS_COURSES", "").split(",") if c.strip()]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SCHEDULER] %(message)s")
logger = logging.getLogger(__name__)

MOODLE_SESSION = None


# ─── Session Moodle ───────────────────────────────────────────────────

def get_moodle_session() -> requests.Session:
    global MOODLE_SESSION
    if MOODLE_SESSION is not None:
        return MOODLE_SESSION
    session = requests.Session()
    login_url = f"{MOODLE_URL}/login/index.php"
    r = session.get(login_url, timeout=30)
    token_match = re.search(r'name="logintoken".*?value="([^"]+)"', r.text)
    logintoken = token_match.group(1) if token_match else ''
    session.post(login_url, data={
        'username': MOODLE_ADMIN_USER,
        'password': MOODLE_ADMIN_PASSWORD,
        'logintoken': logintoken
    }, allow_redirects=True, timeout=30)
    MOODLE_SESSION = session
    logger.info("Session Moodle authentifiée.")
    return session


# ─── Audit log ───────────────────────────────────────────────────────
# get_last_evaluation_time est fourni par backend/audit.py (base SQLite).


# ─── API Moodle ───────────────────────────────────────────────────────

def moodle_api(function: str, params: dict) -> dict:
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    params.update({
        "wstoken": MOODLE_TOKEN,
        "wsfunction": function,
        "moodlewsrestformat": "json",
    })
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_all_courses() -> list:
    result = moodle_api("core_course_get_courses", {})
    if not isinstance(result, list):
        return []
    courses = [c for c in result if c.get("id", 0) > 1]
    if EACHS_COURSES:
        courses = [c for c in courses if c.get("shortname") in EACHS_COURSES]
    return courses


def get_assignments(course_id: int) -> list:
    result = moodle_api("mod_assign_get_assignments", {"courseids[0]": course_id})
    courses = result.get("courses", [])
    if not courses:
        return []
    return courses[0].get("assignments", [])


def get_submissions(assignment_id: int) -> list:
    result = moodle_api("mod_assign_get_submissions", {"assignmentids[0]": assignment_id})
    assignments = result.get("assignments", [])
    if not assignments:
        return []
    return assignments[0].get("submissions", [])


# ─── Extraction soumission ────────────────────────────────────────────

def clean_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()


def download_and_extract_file(fileurl: str, filename: str) -> str:
    try:
        clean_url = fileurl.replace('/webservice/pluginfile.php/', '/pluginfile.php/')
        clean_url = clean_url.split('?')[0]
        session = get_moodle_session()
        response = session.get(clean_url, timeout=30)
        response.raise_for_status()
        if 'application/json' in response.headers.get('content-type', ''):
            global MOODLE_SESSION
            MOODLE_SESSION = None
            session = get_moodle_session()
            response = session.get(clean_url, timeout=30)
        ext = "." + filename.split(".")[-1].lower() if "." in filename else ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name
        from extractor import extract
        result = extract(tmp_path)
        os.unlink(tmp_path)
        if result["success"]:
            logger.info(f"Fichier extrait : {filename} ({result['char_count']} caractères)")
            return result["text"]
        else:
            logger.warning(f"Extraction échouée pour {filename} : {result['error']}")
            return ""
    except Exception as e:
        logger.error(f"Erreur téléchargement {filename} : {e}")
        return ""


def get_submission_text(submission: dict) -> tuple:
    """Retourne (texte, source). Priorité : fichier > texte en ligne."""
    for plugin in submission.get("plugins", []):
        if plugin.get("type") == "file":
            for filearea in plugin.get("fileareas", []):
                files = filearea.get("files", [])
                if files:
                    file_info = files[0]
                    text = download_and_extract_file(
                        file_info.get("fileurl", ""),
                        file_info.get("filename", "")
                    )
                    if text:
                        return text, f"file:{file_info.get('filename', '')}"
    for plugin in submission.get("plugins", []):
        if plugin.get("type") == "onlinetext":
            for editor in plugin.get("editorfields", []):
                if editor.get("name") == "onlinetext":
                    text = clean_html(editor.get("text", ""))
                    if text:
                        return text, "onlinetext"
    return "", "none"


# ─── Génération rubric et détection type ─────────────────────────────
def generate_rubric(question: str, max_score: float) -> str:
    prompt = f"""Tu es un enseignant. Génère un barème court pour cette question.
Question : {question}
Note maximale : {max_score}
Réponds UNIQUEMENT avec le barème en une ligne : "Xpts : critère 1. Xpts : critère 2. Xpts : critère 3."
"""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}
        )
        return response["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"Rubric auto échoué : {e}")
        third = int(max_score / 3)
        return f"{third}pts : pertinence. {third}pts : concepts. {max_score - 2*third}pts : clarté."

# Options d'un questionnaire : « A) … B) … C) … », ou « a. … b. … ».
_OPTIONS_RE = re.compile(r"(?:^|[\s(])([A-Da-d])[)\.]\s+\S")

# Consigne de longueur explicite : signal plus fiable que le verbe de la
# consigne, car « décrivez en une phrase » attend une réponse courte alors que
# le verbe seul oriente vers la rédaction.
_BRIEVETE = ["en une phrase", "en deux phrases", "en une ou deux phrases",
             "en quelques mots", "en quelques lignes", "brièvement",
             "deux phrases maximum", "une phrase maximum", "réponse courte",
             "définition courte"]

_FORMEL = ["démontrez", "prouvez", "calculez", "résolvez", "démonstration",
           "preuve formelle", "exercice formel", "par récurrence"]

_REDACTION = ["expliquez", "décrivez", "discutez", "analysez", "comparez",
              "justifiez", "développez", "dissertez", "rédigez", "présentez",
              "dissertation", "étude de cas"]


def detect_task_type(question: str, title: str = "") -> str:
    """
    Détermine le type de tâche à partir de l'énoncé, et du titre du devoir
    quand il est fourni.

    L'ordre des tests traduit la fiabilité décroissante des indices. La
    présence d'options numérotées est un indice de structure, qui identifie un
    questionnaire même quand l'énoncé ne contient jamais le mot « QCM ». Une
    consigne de longueur explicite passe avant les verbes de consigne, car
    « décrivez en une ou deux phrases » attend une réponse courte. Le repli
    reste conservateur : en cas de doute sur un texte long, la rédaction, qui
    impose la révision humaine.
    """
    texte = f"{title}\n{question}"
    q = texte.lower()

    if any(w in q for w in ["qcm", "choix multiple", "cochez", "sélectionnez",
                            "questionnaire à choix"]):
        return "qcm"
    # Au moins trois propositions distinctes : évite de confondre une
    # énumération ponctuelle avec un questionnaire.
    if len({m.lower() for m in _OPTIONS_RE.findall(texte)}) >= 3:
        return "qcm"

    if any(w in q for w in _FORMEL):
        return "formal"
    if any(w in q for w in _BRIEVETE):
        return "short_answer"
    if any(w in q for w in _REDACTION):
        return "essay"
    return "essay" if len(question) > 100 else "short_answer"


# ─── Envoi à EACHS et écriture dans Moodle ───────────────────────────

def send_to_eachs(student_id, assignment_id, question, rubric, task_type,
                  student_answer, max_score, course_name="", assignment_name="", student_name=""):
    payload = {
        "student_id": student_id,
        "assignment_id": assignment_id,
        "task_type": task_type,
        "question": question,
        "rubric": rubric,
        "student_answer": student_answer,
        "max_score": max_score,
        "course_name": course_name,
        "assignment_name": assignment_name,
        "student_name": student_name,
    }
    response = requests.post(f"{EACHS_URL}/evaluate", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()


def write_grade_to_moodle(assignment_id, user_id, grade, feedback):
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    params = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "mod_assign_save_grade",
        "moodlewsrestformat": "json",
        "assignmentid": assignment_id,
        "userid": user_id,
        "grade": grade,
        "attemptnumber": -1,
        "addattempt": 0,
        "workflowstate": "released",
        "applytoall": 0,
        "plugindata[assignfeedbackcomments_editor][text]": f"[EACHS - Proposition IA] {feedback}",
        "plugindata[assignfeedbackcomments_editor][format]": 1,
    }
    response = requests.post(url, params=params, timeout=30)
    response.raise_for_status()


# ─── Boucle principale ────────────────────────────────────────────────

def check_new_submissions():
    logger.info("Vérification des nouvelles soumissions...")
    new_count = 0

    try:
        courses = get_all_courses()
        for course in courses:
            course_id = course["id"]
            course_name = course.get("shortname", str(course_id))

            try:
                assignments = get_assignments(course_id)
            except Exception:
                continue

            for assignment in assignments:
                assignment_id = assignment["id"]
                assignment_name = assignment["name"]
                max_score = float(assignment.get("grade", 100))
                question = clean_html(assignment.get("intro", "")) or assignment_name

                try:
                    submissions = get_submissions(assignment_id)
                except Exception:
                    continue

                for submission in submissions:
                    if submission.get("status") != "submitted":
                        continue

                    user_id = submission["userid"]
                    submission_modified = submission.get("timemodified", 0)

                    # Vérifier si la soumission a été modifiée depuis la dernière évaluation
                    last_eval = get_last_evaluation_time(assignment_id, user_id)
                    if last_eval > 0 and submission_modified <= last_eval:
                        continue  # Pas modifiée, on passe

                    student_answer, source = get_submission_text(submission)
                    if not student_answer:
                        logger.info(f"Soumission vide ignorée : {assignment_id}_{user_id}")
                        continue

                    if last_eval > 0:
                        logger.info(f"Soumission modifiée détectée : cours={course_name} | devoir={assignment_name} | étudiant={user_id}")
                    else:
                        logger.info(f"Nouvelle soumission : cours={course_name} | devoir={assignment_name} | étudiant={user_id} | source={source}")

                    rubric = generate_rubric(question, max_score)
                    task_type = detect_task_type(question, assignment_name)
                    logger.info(f"Type={task_type} | Rubric={rubric[:60]}...")
                    student_name = get_student_name(user_id)


                    try:
                        result = send_to_eachs(
                            student_id=str(user_id),
                            assignment_id=str(assignment_id),
                            question=question,
                            rubric=rubric,
                            task_type=task_type,
                            student_answer=student_answer,
                            max_score=max_score,
                            course_name=course_name,
                            assignment_name=assignment_name,
                            student_name=student_name,
                        )

                        write_grade_to_moodle(
                            assignment_id=assignment_id,
                            user_id=user_id,
                            grade=result["proposed_score"],
                            feedback=result["feedback"]
                        )

                        new_count += 1
                        logger.info(f"✓ Score={result['proposed_score']}/{max_score} | confiance={result['confidence']} | révision={result['requires_human_review']} | log_id={result['log_id']}")

                    except Exception as e:
                        logger.error(f"Erreur traitement {assignment_id}_{user_id} : {e}")

    except Exception as e:
        logger.error(f"Erreur générale : {e}")

    logger.info(f"{new_count} soumission(s) traitée(s)." if new_count > 0 else "Aucune nouvelle soumission.")


def get_student_name(user_id: int) -> str:
    """Récupère le nom complet d'un étudiant depuis Moodle."""
    try:
        result = moodle_api("core_user_get_users", {
            "criteria[0][key]": "id",
            "criteria[0][value]": user_id
        })
        users = result.get("users", [])
        if users:
            return f"{users[0].get('firstname', '')} {users[0].get('lastname', '')}".strip()
    except:
        pass
    return f"Étudiant {user_id}"

# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    perimetre = ", ".join(EACHS_COURSES) if EACHS_COURSES else "tous les cours"
    logger.info(f"Démarrage — intervalle={CHECK_INTERVAL}s | backend={AI_BACKEND} | moodle={MOODLE_URL}")
    logger.info(f"Périmètre d'activation : {perimetre}")

    get_moodle_session()
    check_new_submissions()

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_new_submissions, "interval", seconds=CHECK_INTERVAL)
    scheduler.start()

    logger.info(f"Scheduler actif. Vérification toutes les {CHECK_INTERVAL}s. Ctrl+C pour arrêter.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("Scheduler arrêté.")