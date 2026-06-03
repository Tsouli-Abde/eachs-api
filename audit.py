import json
import uuid
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("audit_log.json")


def _load_logs() -> list:
    if not LOG_FILE.exists():
        return []
    with open(LOG_FILE, "r") as f:
        return json.load(f)


def _save_logs(logs: list):
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def write_log(request, result: dict) -> str:
    logs = _load_logs()

    # Mettre à jour le log existant si même étudiant + même devoir
    existing_idx = None
    for i, l in enumerate(logs):
        if (l.get("assignment_id") == str(request.assignment_id) and
                l.get("student_id") == str(request.student_id)):
            existing_idx = i
            break

    if existing_idx is not None:
        log_id = logs[existing_idx]["log_id"]
        logs[existing_idx].update({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "task_type": request.task_type.value,
            "question": request.question,
            "student_answer": request.student_answer,
            "student_answer_preview": request.student_answer[:200],
            "prompt_version": result.get("prompt_version", "unknown"),
            "prompt_used": result.get("prompt_used", ""),
            "proposed_score": result["proposed_score"],
            "max_score": request.max_score,
            "confidence": result["confidence"],
            "feedback": result["feedback"],
            "requires_human_review": result["requires_human_review"],
            "backend": result.get("backend", "unknown"),
            "course_name": getattr(request, "course_name", ""),
            "assignment_name": getattr(request, "assignment_name", ""),
            # Réinitialiser la décision humaine car la réponse a changé
            "human_final_score": None,
            "human_decision": None,
            "human_comment": None,
            "reviewed_at": None,
            "student_name": getattr(request, "student_name", ""),
        })
    else:
        log_id = str(uuid.uuid4())
        entry = {
            "log_id": log_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "student_id": str(request.student_id),
            "assignment_id": str(request.assignment_id),
            "task_type": request.task_type.value,
            "question": request.question,
            "student_answer": request.student_answer,
            "student_answer_preview": request.student_answer[:200],
            "prompt_version": result.get("prompt_version", "unknown"),
            "prompt_used": result.get("prompt_used", ""),
            "proposed_score": result["proposed_score"],
            "max_score": request.max_score,
            "confidence": result["confidence"],
            "feedback": result["feedback"],
            "requires_human_review": result["requires_human_review"],
            "backend": result.get("backend", "unknown"),
            "course_name": getattr(request, "course_name", ""),
            "assignment_name": getattr(request, "assignment_name", ""),
            "human_final_score": None,
            "human_decision": None,
            "human_comment": None,
            "reviewed_at": None,
            "student_name": getattr(request, "student_name", ""),
        }
        logs.append(entry)

    _save_logs(logs)
    return log_id


def update_human_decision(log_id: str, final_score: float, decision: str, comment: str = "") -> bool:
    logs = _load_logs()
    for entry in logs:
        if entry["log_id"] == log_id:
            entry["human_final_score"] = final_score
            entry["human_decision"] = decision
            entry["human_comment"] = comment
            entry["reviewed_at"] = datetime.utcnow().isoformat() + "Z"
            _save_logs(logs)
            return True
    return False


def get_all_logs() -> list:
    return _load_logs()