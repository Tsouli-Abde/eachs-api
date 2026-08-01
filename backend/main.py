import os
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
from models import EvaluationRequest, EvaluationResponse
from evaluator import evaluate
from audit import write_log, update_human_decision, get_all_logs
from collections import defaultdict
from fastapi.responses import HTMLResponse, FileResponse
import tempfile
import shutil

# Le dashboard web est servi depuis le dossier dashboard/ à la racine du projet,
# indépendamment du répertoire de lancement de l'API.
BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"

app = FastAPI(
    title="EACHS API",
    description="Évaluation Assistée sous Contrôle Humain Structuré",
    version="0.1.0",
)

MOODLE_URL = os.environ.get("MOODLE_URL", "http://localhost:8080")
MOODLE_TOKEN = os.environ.get("MOODLE_TOKEN")


# ─── Helpers Moodle ───────────────────────────────────────────────────

def write_grade_to_moodle(assignment_id: int, user_id: int, grade: float, feedback: str):
    """Écrit une note et un feedback dans Moodle."""
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
        "plugindata[assignfeedbackcomments_editor][text]": feedback,
        "plugindata[assignfeedbackcomments_editor][format]": 1,
    }
    try:
        response = requests.post(url, params=params, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[MOODLE] Avertissement : impossible de mettre à jour Moodle : {e}")


def build_moodle_feedback(decision: str, ai_score: float, final_score: float,
                           max_score: float, ai_feedback: str, prof_comment: str = "") -> str:
    """Construit le feedback Moodle selon la décision du prof."""
    if decision == "validated":
        header = f"✓ Score validé par l'enseignant : {final_score}/{max_score}"
        body = f"{ai_feedback}"
        note = "[Évaluation IA revue et approuvée par l'enseignant (AI Act, art. 14)]"
    elif decision == "modified":
        header = f"✎ Score modifié par l'enseignant : {final_score}/{max_score} (IA proposait {ai_score}/{max_score})"
        body = f"{ai_feedback}"
        note = "[Score ajusté après révision humaine (AI Act, art. 14)]"
    elif decision == "rejected":
        header = f"⚠ Évaluation IA rejetée, correction manuelle en cours"
        body = "L'enseignant a estimé que cette copie nécessite une correction entièrement manuelle."
        note = "[Évaluation automatique non retenue (AI Act, art. 14)]"
    else:
        header = ""
        body = ai_feedback
        note = ""

    parts = [header, body]
    if prof_comment:
        parts.append(f"Note de l'enseignant : {prof_comment}")
    parts.append(note)
    return "\n\n".join(p for p in parts if p)


# ─── Endpoints ───────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "EACHS API v0.1"}


@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate_submission(request: EvaluationRequest):
    try:
        result = evaluate(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'évaluation : {str(e)}")

    log_id = write_log(request, result)

    return EvaluationResponse(
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        task_type=request.task_type,
        proposed_score=result["proposed_score"],
        max_score=request.max_score,
        confidence=result["confidence"],
        feedback=result["feedback"],
        requires_human_review=result["requires_human_review"],
        log_id=log_id,
        backend=result.get("backend"),
        prompt_version=result.get("prompt_version"),
        manipulation_detected=result.get("manipulation_detected", False),
    )


@app.post("/evaluate/file")
async def evaluate_file_submission(
    student_id: str = Form(...),
    assignment_id: str = Form(...),
    task_type: str = Form(...),
    question: str = Form(...),
    max_score: float = Form(100.0),
    rubric: str = Form(""),
    expected_answer: str = Form(""),
    file: UploadFile = File(...),
):
    suffix = "." + file.filename.split(".")[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    from extractor import extract
    extraction = extract(tmp_path)
    os.unlink(tmp_path)

    if not extraction["success"]:
        raise HTTPException(status_code=400, detail=f"Extraction échouée : {extraction['error']}")

    if extraction["requires_multimodal"]:
        raise HTTPException(status_code=422, detail="Image reçue mais pytesseract non disponible.")

    from models import TaskType as TT
    request = EvaluationRequest(
        student_id=student_id,
        assignment_id=assignment_id,
        task_type=TT(task_type),
        question=question,
        expected_answer=expected_answer or None,
        rubric=rubric or None,
        student_answer=extraction["text"],
        max_score=max_score,
    )

    try:
        result = evaluate(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'évaluation : {str(e)}")

    log_id = write_log(request, result)

    return EvaluationResponse(
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        task_type=request.task_type,
        proposed_score=result["proposed_score"],
        max_score=request.max_score,
        confidence=result["confidence"],
        feedback=result["feedback"],
        requires_human_review=result["requires_human_review"],
        log_id=log_id,
        backend=result.get("backend"),
        file_type=extraction["file_type"],
        prompt_version=result.get("prompt_version"),
        manipulation_detected=result.get("manipulation_detected", False),
    )


class HumanReview(BaseModel):
    final_score: float
    decision: str  # "validated", "modified", "rejected"
    prof_comment: Optional[str] = ""
    reviewer_id: Optional[str] = "enseignant_1"  # PROV : agent enseignant identifiable


@app.post("/review/{log_id}")
def submit_human_review(log_id: str, review: HumanReview):
    if review.decision not in ["validated", "modified", "rejected"]:
        raise HTTPException(status_code=400, detail="Decision must be: validated, modified, or rejected")

    success = update_human_decision(log_id, review.final_score, review.decision,
                                    review.prof_comment, review.reviewer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Log ID not found")

    # Mettre à jour Moodle selon la décision
    logs = get_all_logs()
    log = next((l for l in logs if l["log_id"] == log_id), None)

    if log:
        try:
            assignment_id = int(log["assignment_id"])
            user_id = int(log["student_id"])

            if review.decision == "validated":
                # Note IA validée par le prof
                feedback = build_moodle_feedback(
                    "validated",
                    log["proposed_score"], review.final_score, log["max_score"],
                    log.get("feedback", ""), review.prof_comment or ""
                )
                write_grade_to_moodle(assignment_id, user_id, review.final_score, feedback)

            elif review.decision == "modified":
                # Note modifiée par le prof
                feedback = build_moodle_feedback(
                    "modified",
                    log["proposed_score"], review.final_score, log["max_score"],
                    log.get("feedback", ""), review.prof_comment or ""
                )
                write_grade_to_moodle(assignment_id, user_id, review.final_score, feedback)

            elif review.decision == "rejected":
                # Note rejetée — note provisoire 0, message d'attente
                feedback = build_moodle_feedback(
                    "rejected",
                    log["proposed_score"], 0, log["max_score"],
                    log.get("feedback", ""), review.prof_comment or ""
                )
                write_grade_to_moodle(assignment_id, user_id, 0, feedback)

        except Exception as e:
            print(f"[REVIEW] Avertissement Moodle : {e}")

    return {"status": "ok", "log_id": log_id, "decision": review.decision}


@app.get("/logs")
def list_logs():
    return get_all_logs()


@app.get("/stats")
def get_stats():
    logs = get_all_logs()
    if not logs:
        return {"message": "Aucune donnée disponible"}

    total = len(logs)
    reviewed = [l for l in logs if l["human_decision"] is not None]
    validated = [l for l in reviewed if l["human_decision"] == "validated"]
    modified = [l for l in reviewed if l["human_decision"] == "modified"]
    rejected = [l for l in reviewed if l["human_decision"] == "rejected"]
    pending = [l for l in logs if l["requires_human_review"] and l["human_decision"] is None]

    by_task = defaultdict(lambda: {
        "total": 0, "requires_review": 0, "reviewed": 0,
        "validated": 0, "modified": 0, "rejected": 0,
        "avg_ai_score_pct": [], "avg_human_score_pct": []
    })

    for l in logs:
        tt = l["task_type"]
        by_task[tt]["total"] += 1
        if l["requires_human_review"]:
            by_task[tt]["requires_review"] += 1
        if l["human_decision"]:
            by_task[tt]["reviewed"] += 1
            by_task[tt][l["human_decision"]] += 1
        if l["max_score"] and l["max_score"] > 0:
            by_task[tt]["avg_ai_score_pct"].append(l["proposed_score"] / l["max_score"] * 100)
            if l["human_final_score"] is not None:
                by_task[tt]["avg_human_score_pct"].append(l["human_final_score"] / l["max_score"] * 100)

    task_summary = {}
    for tt, data in by_task.items():
        ai_scores = data["avg_ai_score_pct"]
        human_scores = data["avg_human_score_pct"]
        task_summary[tt] = {
            "total_evaluations": data["total"],
            "requires_human_review": data["requires_review"],
            "reviewed": data["reviewed"],
            "validated": data["validated"],
            "modified": data["modified"],
            "rejected": data["rejected"],
            "modification_rate_pct": round(data["modified"] / data["reviewed"] * 100, 1) if data["reviewed"] > 0 else None,
            "avg_ai_score_pct": round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else None,
            "avg_human_score_pct": round(sum(human_scores) / len(human_scores), 1) if human_scores else None,
        }

    return {
        "global": {
            "total_evaluations": total,
            "total_reviewed": len(reviewed),
            "pending_review": len(pending),
            "validated": len(validated),
            "modified": len(modified),
            "rejected": len(rejected),
            "modification_rate_pct": round(len(modified) / len(reviewed) * 100, 1) if reviewed else None,
        },
        "by_task_type": task_summary,
    }


@app.get("/stats/kappa")
def get_kappa():
    logs = get_all_logs()
    # Un rejet signifie « je refuse cette évaluation », pas « la note est 0 » :
    # la note provisoire nulle n'est pas un jugement de l'enseignant sur la
    # copie. L'inclure fabriquerait un désaccord maximal qui effondre le kappa.
    excluded_rejected = [l for l in logs if l["human_decision"] == "rejected"]
    reviewed = [l for l in logs
                if l["human_final_score"] is not None
                and l["human_decision"] != "rejected"
                and l["max_score"] > 0]

    if len(reviewed) < 2:
        return {"message": "Pas assez de données pour calculer le kappa (minimum 2 évaluations révisées)"}

    def to_ordinal(score, max_score):
        pct = score / max_score
        if pct <= 0.2: return 0
        elif pct <= 0.4: return 1
        elif pct <= 0.6: return 2
        elif pct <= 0.8: return 3
        else: return 4

    n_categories = 5
    n = len(reviewed)
    ai_ratings = [to_ordinal(l["proposed_score"], l["max_score"]) for l in reviewed]
    human_ratings = [to_ordinal(l["human_final_score"], l["max_score"]) for l in reviewed]

    confusion = [[0] * n_categories for _ in range(n_categories)]
    for ai, human in zip(ai_ratings, human_ratings):
        confusion[ai][human] += 1

    weights = [[((i - j) ** 2) / ((n_categories - 1) ** 2) for j in range(n_categories)] for i in range(n_categories)]
    row_sum = [sum(confusion[i]) for i in range(n_categories)]
    col_sum = [sum(confusion[i][j] for i in range(n_categories)) for j in range(n_categories)]
    expected = [[row_sum[i] * col_sum[j] / n for j in range(n_categories)] for i in range(n_categories)]

    observed_disagreement = sum(weights[i][j] * confusion[i][j] for i in range(n_categories) for j in range(n_categories)) / n
    expected_disagreement = sum(weights[i][j] * expected[i][j] for i in range(n_categories) for j in range(n_categories)) / n

    kappa = 1.0 if expected_disagreement == 0 else 1 - (observed_disagreement / expected_disagreement)

    if kappa < 0.4: interpretation = "Accord faible : supervision humaine renforcée recommandée"
    elif kappa < 0.6: interpretation = "Accord modéré : validation humaine systématique nécessaire"
    elif kappa < 0.8: interpretation = "Accord substantiel : le système est fiable avec validation"
    else: interpretation = "Accord quasi parfait : le système peut opérer avec supervision allégée"

    return {
        "n_evaluated": n,
        "quadratic_weighted_kappa": round(kappa, 4),
        "interpretation": interpretation,
        # Explicité pour l'audit : la valeur du kappa dépend de la façon dont
        # les notes continues sont ramenées sur une échelle ordinale.
        "discretisation": f"{n_categories} classes de {round(100 / n_categories)}% de la note maximale",
        "excluded_rejected": len(excluded_rejected),
        "pairs": [
            {
                "log_id": l["log_id"],
                "task_type": l["task_type"],
                "ai_score": l["proposed_score"],
                "human_score": l["human_final_score"],
                "max_score": l["max_score"],
                "ai_ordinal": ai_ratings[i],
                "human_ordinal": human_ratings[i],
            }
            for i, l in enumerate(reviewed)
        ]
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (DASHBOARD_DIR / "dashboard.html").read_text(encoding="utf-8")

@app.get("/dashboard.charts.js")
def charts_js():
    return FileResponse(DASHBOARD_DIR / "dashboard.charts.js", media_type="application/javascript")

@app.get("/dashboard.demo.js")
def demo_js():
    return FileResponse(DASHBOARD_DIR / "dashboard.demo.js", media_type="application/javascript")

@app.get("/dashboard.app.js")
def app_js():
    return FileResponse(DASHBOARD_DIR / "dashboard.app.js", media_type="application/javascript")

@app.get("/favicon.svg")
def favicon():
    return FileResponse(DASHBOARD_DIR / "favicon.svg", media_type="image/svg+xml")