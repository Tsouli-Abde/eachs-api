"""
migrate_json_to_sqlite.py — Migre un ancien audit_log.json vers la base SQLite.

Usage :
    python scripts/migrate_json_to_sqlite.py [chemin/vers/audit_log.json]

Idempotent : relancer ne duplique pas (clé primaire log_id).
Le fichier JSON n'est pas modifié ; à archiver après vérification.
La base cible est backend/../data/audit_log.sqlite (gérée par backend/audit.py).
"""

import json
import sys
from pathlib import Path

# Accès au module d'audit du backend (base SQLite).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from audit import insert_raw, get_all_logs

src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("audit_log.json")
if not src.exists():
    sys.exit(f"Fichier introuvable : {src}")

content = src.read_text(encoding="utf-8-sig").strip()
entries = json.loads(content) if content else []
print(f"{len(entries)} entrées dans {src}")

for e in entries:
    e.setdefault("reviewer_id", None)
    e.setdefault("manipulation_detected", False)
    insert_raw(e)

print(f"Migration terminée : {len(get_all_logs())} enregistrements en base.")
