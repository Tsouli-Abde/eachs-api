import os
import json
import ollama
from google import genai
from dotenv import load_dotenv
from models import TaskType

load_dotenv()

# Switch entre local et cloud dans le .env
# AI_BACKEND=local  -> Ollama + Mistral
# AI_BACKEND=cloud  -> Gemini
AI_BACKEND = os.environ.get("AI_BACKEND", "local")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Version du prompt — à incrémenter à chaque modification
PROMPT_VERSION = "1.1.0"

# Révision humaine systématique par type de tâche
REQUIRES_REVIEW = {
    TaskType.QCM: False,
    TaskType.SHORT_ANSWER: False,
    TaskType.ESSAY: True,
    TaskType.FORMAL: True,
}


def build_prompt(request) -> str:
    base = f"""Tu es un correcteur pédagogique. Évalue la réponse suivante de manière objective.

Type de tâche : {request.task_type.value}
Question posée : {request.question}
"""
    if request.expected_answer:
        base += f"Réponse attendue : {request.expected_answer}\n"
    if request.rubric:
        base += f"Barème / critères : {request.rubric}\n"

    base += f"Réponse de l'étudiant : {request.student_answer}\n"
    base += "Sois particulièrement attentif à la précision technique des termes utilisés.\n"
    base += f"""Note maximale : {request.max_score}

Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ou après, sans balises markdown, avec exactement ces champs :
{{
  "score": <nombre entre 0 et {request.max_score}>,
  "feedback": "<feedback constructif en français, 2-4 phrases>",
  "confidence": "<'high' si tu es certain, 'medium' si quelques doutes, 'low' si la tâche est complexe ou ambiguë>"
}}"""
    return base


def parse_response(raw: str) -> dict:
    """Nettoie et parse la réponse JSON du modèle."""
    raw = raw.strip()
    # Supprimer les balises markdown si présentes
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break
    # Trouver le JSON dans la réponse
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]
    return json.loads(raw)


def evaluate_with_ollama(prompt: str) -> dict:
    """Évaluation via Ollama (local)."""
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1}
    )
    raw = response["message"]["content"]
    return parse_response(raw)


def evaluate_with_gemini(prompt: str) -> dict:
    """Évaluation via Gemini (cloud)."""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return parse_response(response.text)


def evaluate(request) -> dict:
    prompt = build_prompt(request)

    if AI_BACKEND == "local":
        result = evaluate_with_ollama(prompt)
        backend_used = f"ollama/{OLLAMA_MODEL}"
    else:
        result = evaluate_with_gemini(prompt)
        backend_used = f"gemini/{GEMINI_MODEL}"

    requires_review = REQUIRES_REVIEW.get(request.task_type, True)
    if result.get("confidence") == "low":
        requires_review = True

    return {
        "proposed_score": float(result["score"]),
        "feedback": result["feedback"],
        "confidence": result.get("confidence", "medium"),
        "requires_human_review": requires_review,
        "prompt_version": PROMPT_VERSION,
        "prompt_used": prompt,
        "backend": backend_used,
    }