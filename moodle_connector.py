import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

MOODLE_URL = os.environ.get("MOODLE_URL", "http://localhost:8080")
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN")
EACHS_URL = "http://localhost:8000"


def moodle_api(function: str, params: dict) -> dict:
    """Appel générique à l'API REST Moodle."""
    url = f"{MOODLE_URL}/webservice/rest/server.php"
    params.update({
        "wstoken": MOODLE_TOKEN,
        "wsfunction": function,
        "moodlewsrestformat": "json",
    })
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_courses() -> list:
    """Récupère la liste des cours."""
    result = moodle_api("core_course_get_courses", {})
    return result


def get_assignments(course_id: int) -> list:
    """Récupère les devoirs d'un cours."""
    result = moodle_api("mod_assign_get_assignments", {
        "courseids[0]": course_id
    })
    return result.get("courses", [])


def get_submissions(assignment_id: int) -> list:
    """Récupère les soumissions d'un devoir."""
    result = moodle_api("mod_assign_get_submissions", {
        "assignmentids[0]": assignment_id
    })
    assignments = result.get("assignments", [])
    if not assignments:
        return []
    return assignments[0].get("submissions", [])


def get_submission_text(submission: dict) -> str:
    """Extrait le texte d'une soumission en ligne."""
    for plugin in submission.get("plugins", []):
        if plugin.get("type") == "onlinetext":
            for editor in plugin.get("editorfields", []):
                if editor.get("name") == "onlinetext":
                    # Nettoyer les balises HTML
                    text = editor.get("text", "").strip()
                    # Supprimer les tags HTML basiques
                    import re
                    text = re.sub(r'<[^>]+>', '', text).strip()
                    return text
    return ""


def send_to_eachs(student_id: str, assignment_id: str, question: str, student_answer: str) -> dict:
    payload = {
        "student_id": student_id,
        "assignment_id": assignment_id,
        "task_type": "short_answer",
        "question": question,
        "rubric": "40pts : définition correcte des 3 métriques. 30pts : compréhension des cas d'usage de chacune. 30pts : explication du F1-Score comme compromis entre précision et recall.",
        "student_answer": student_answer,
        "max_score": 100.0
    }
    response = requests.post(f"{EACHS_URL}/evaluate", json=payload)
    response.raise_for_status()
    return response.json()


def write_grade_to_moodle(assignment_id: int, user_id: int, grade: float, feedback: str):
    """Écrit une note et un feedback dans Moodle via l'API REST."""
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
    response = requests.post(url, params=params)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print("=== EACHS Moodle Connector ===\n")

    # 1. Récupérer les cours
    print("1. Récupération des cours...")
    courses = get_courses()
    for course in courses:
        if course.get("id", 0) > 1:  # ignorer le cours "Site" (id=1)
            print(f"   Cours trouvé : [{course['id']}] {course['fullname']}")

    # 2. Récupérer les devoirs du cours EACHS01
    target_course = next((c for c in courses if c.get("shortname") == "ML01"), None)
    if not target_course:
        print("Cours EACHS01 non trouvé.")
        exit(1)

    course_id = target_course["id"]
    print(f"\n2. Récupération des devoirs du cours {course_id}...")
    course_assignments = get_assignments(course_id)

    if not course_assignments:
        print("Aucun devoir trouvé.")
        exit(1)

    assignment = next((a for a in course_assignments[0]["assignments"] if a["id"] == 3), None)
    assignment_id = assignment["id"]
    assignment_name = assignment["name"]
    print(f"   Devoir trouvé : [{assignment_id}] {assignment_name}")

    # 3. Récupérer les soumissions
    print(f"\n3. Récupération des soumissions...")
    submissions = get_submissions(assignment_id)

    if not submissions:
        print("   Aucune soumission trouvée. Soumets d'abord un devoir dans Moodle.")
        exit(0)

    print(f"   {len(submissions)} soumission(s) trouvée(s)")

    # 4. Évaluer chaque soumission
    question = "Explique moi la différence entre la précision, le recall et le F1-Score ?"


    for submission in submissions:
        user_id = submission["userid"]
        student_answer = get_submission_text(submission)

        if not student_answer:
            print(f"   Étudiant {user_id} : soumission vide, ignorée.")
            continue

        print(f"\n4. Évaluation de la soumission de l'étudiant {user_id}...")
        print(f"   Réponse : {student_answer[:100]}...")

        result = send_to_eachs(
            student_id=str(user_id),
            assignment_id=str(assignment_id),
            question=question,
            student_answer=student_answer
        )

        print(f"   Score proposé : {result['proposed_score']}/{result['max_score']}")
        print(f"   Confiance : {result['confidence']}")
        print(f"   Révision humaine requise : {result['requires_human_review']}")
        print(f"   Log ID : {result['log_id']}")

        # 5. Écrire la note dans Moodle
        print(f"\n5. Écriture de la note dans Moodle...")
        write_grade_to_moodle(
            assignment_id=assignment_id,
            user_id=user_id,
            grade=result["proposed_score"],
            feedback=result["feedback"]
        )
        print(f"   Note écrite : {result['proposed_score']}/10 pour l'étudiant {user_id}")

    print("\n=== Traitement terminé ===")
    print(f"Consultez http://localhost:8000/logs pour l'audit trail complet.")