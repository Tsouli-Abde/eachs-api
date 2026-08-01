from pydantic import BaseModel
from typing import Optional
from enum import Enum


class TaskType(str, Enum):
    QCM = "qcm"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    FORMAL = "formal"


class EvaluationRequest(BaseModel):
    student_id: str
    assignment_id: str
    task_type: TaskType
    question: str
    expected_answer: Optional[str] = None
    rubric: Optional[str] = None
    student_answer: str
    max_score: float = 100.0
    course_name: Optional[str] = ""
    assignment_name: Optional[str] = ""
    student_name: Optional[str] = ""



class EvaluationResponse(BaseModel):
    student_id: str
    assignment_id: str
    task_type: TaskType
    proposed_score: float
    max_score: float
    confidence: str
    feedback: str
    requires_human_review: bool
    log_id: str
    backend: Optional[str] = None
    file_type: Optional[str] = None
    # Contexte technique remonté à l'appelant : le versionnement du prompt est
    # une exigence d'audit trail, et manipulation_detected permet de mesurer la
    # robustesse depuis un client externe (campagnes de red teaming).
    prompt_version: Optional[str] = None
    manipulation_detected: bool = False