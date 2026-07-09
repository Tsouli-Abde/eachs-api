"""
audit.py — Journal d'audit EACHS sur SQLite.

Remplace l'ancienne persistance JSON (audit_log.json) par une base SQLite :
- thread-safe (transactions), pas de corruption en écriture concurrente
  (l'API et le scheduler écrivent en parallèle) ;
- append/upsert par (student_id, assignment_id) : une nouvelle soumission
  du même étudiant sur le même devoir met à jour son enregistrement ;
- même structure de champs qu'avant + reviewer_id (identifiant du réviseur,
  qui complète le graphe PROV : l'agent enseignant devient identifiable).

L'interface publique est IDENTIQUE à l'ancien audit.py :
    write_log(request, result) -> log_id
    update_human_decision(log_id, final_score, decision, comment, reviewer_id)
    get_all_logs() -> list
main.py et scheduler.py fonctionnent donc sans changer leurs imports.

La base est stockée dans <racine du projet>/data/audit_log.sqlite.
Migration depuis un ancien audit_log.json :
    python scripts/migrate_json_to_sqlite.py audit_log.json
"""

import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

# Base rangée dans data/ à la racine du projet (backend/ -> racine).
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = DATA_DIR / "audit_log.sqlite"

_lock = threading.Lock()

FIELDS = [
    "log_id", "timestamp", "student_id", "student_name",
    "assignment_id", "assignment_name", "course_name", "task_type",
    "question", "student_answer", "student_answer_preview",
    "prompt_version", "prompt_used",
    "proposed_score", "max_score", "confidence", "feedback",
    "requires_human_review", "backend", "manipulation_detected",
    "human_final_score", "human_decision", "human_comment", "reviewed_at",
    "reviewer_id",  # nouveau : identifiant du réviseur (PROV : agent enseignant)
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    student_id TEXT, student_name TEXT,
    assignment_id TEXT, assignment_name TEXT, course_name TEXT,
    task_type TEXT,
    question TEXT, student_answer TEXT, student_answer_preview TEXT,
    prompt_version TEXT, prompt_used TEXT,
    proposed_score REAL, max_score REAL,
    confidence TEXT, feedback TEXT,
    requires_human_review INTEGER, backend TEXT,
    manipulation_detected INTEGER,
    human_final_score REAL, human_decision TEXT,
    human_comment TEXT, reviewed_at TEXT,
    reviewer_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_assignment ON audit_log (assignment_id);
CREATE INDEX IF NOT EXISTS idx_student    ON audit_log (student_id);
CREATE INDEX IF NOT EXISTS idx_tasktype   ON audit_log (task_type);
"""


def _conn():
    c = sqlite3.connect(DB_FILE, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def _row_to_dict(row):
    d = dict(row)
    d["requires_human_review"] = bool(d["requires_human_review"])
    d["manipulation_detected"] = bool(d["manipulation_detected"])
    return d


def insert_raw(entry: dict) -> None:
    """Insère/remplace un enregistrement complet (migration, mark_done)."""
    data = {k: entry.get(k) for k in FIELDS}
    data["requires_human_review"] = int(bool(data.get("requires_human_review")))
    data["manipulation_detected"] = int(bool(data.get("manipulation_detected")))
    cols = ", ".join(FIELDS)
    marks = ", ".join("?" for _ in FIELDS)
    with _lock, _conn() as c:
        c.execute(f"INSERT OR REPLACE INTO audit_log ({cols}) VALUES ({marks})",
                  [data[k] for k in FIELDS])


def write_log(request, result: dict) -> str:
    """
    Enregistre une évaluation.
    Upsert par (student_id, assignment_id) : une nouvelle soumission du même
    étudiant sur le même devoir met à jour l'enregistrement existant et
    réinitialise la décision humaine (la réponse a changé).
    Signature identique à l'ancien audit.py — main.py n'a rien à changer.
    """
    student_id = str(request.student_id)
    assignment_id = str(request.assignment_id)
    now = datetime.utcnow().isoformat() + "Z"

    common = {
        "timestamp": now,
        "student_id": student_id,
        "student_name": getattr(request, "student_name", ""),
        "assignment_id": assignment_id,
        "assignment_name": getattr(request, "assignment_name", ""),
        "course_name": getattr(request, "course_name", ""),
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
        "requires_human_review": int(bool(result["requires_human_review"])),
        "backend": result.get("backend", "unknown"),
        "manipulation_detected": int(bool(result.get("manipulation_detected"))),
        # la réponse a changé -> on repart d'une décision humaine vierge
        "human_final_score": None,
        "human_decision": None,
        "human_comment": None,
        "reviewed_at": None,
        "reviewer_id": None,
    }

    with _lock, _conn() as c:
        row = c.execute(
            "SELECT log_id FROM audit_log WHERE assignment_id = ? AND student_id = ?",
            (assignment_id, student_id),
        ).fetchone()

        if row:
            log_id = row["log_id"]
            sets = ", ".join(f"{k} = ?" for k in common)
            c.execute(f"UPDATE audit_log SET {sets} WHERE log_id = ?",
                      list(common.values()) + [log_id])
        else:
            log_id = str(uuid.uuid4())
            entry = {"log_id": log_id, **common}
            cols = ", ".join(FIELDS)
            marks = ", ".join("?" for _ in FIELDS)
            c.execute(f"INSERT INTO audit_log ({cols}) VALUES ({marks})",
                      [entry.get(k) for k in FIELDS])

    return log_id


def update_human_decision(log_id: str, final_score: float, decision: str,
                          comment: str = "", reviewer_id: str = None) -> bool:
    """Enregistre la décision humaine (validated / modified / rejected)."""
    with _lock, _conn() as c:
        cur = c.execute(
            "UPDATE audit_log SET human_final_score = ?, human_decision = ?, "
            "human_comment = ?, reviewed_at = ?, reviewer_id = ? WHERE log_id = ?",
            (final_score, decision, comment,
             datetime.utcnow().isoformat() + "Z", reviewer_id, log_id),
        )
        return cur.rowcount > 0


def get_all_logs() -> list:
    with _conn() as c:
        rows = c.execute("SELECT * FROM audit_log ORDER BY timestamp").fetchall()
    return [_row_to_dict(r) for r in rows]


def get_log(log_id: str):
    with _conn() as c:
        row = c.execute("SELECT * FROM audit_log WHERE log_id = ?",
                        (log_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_last_evaluation_time(assignment_id, user_id) -> float:
    """
    Timestamp Unix de la dernière évaluation pour cette soumission
    (utilisé par le scheduler pour ne pas réévaluer une copie inchangée).
    """
    with _conn() as c:
        row = c.execute(
            "SELECT timestamp FROM audit_log WHERE assignment_id = ? AND student_id = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (str(assignment_id), str(user_id)),
        ).fetchone()
    if not row or not row["timestamp"]:
        return 0.0
    try:
        dt = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return 0.0


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


if __name__ == "__main__":
    print(f"Base : {DB_FILE}")
    logs = get_all_logs()
    print(f"{len(logs)} enregistrements")
