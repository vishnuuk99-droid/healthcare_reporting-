"""
Decision store – CRUD operations for organizational SME decisions.

Persists decisions to knowledge/org_decisions.json and provides
helpers for listing, updating, and deleting entries.

Supports versioned change tracking with author attribution.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from modules.schemas import OrgDecision
from modules.file_manager import KNOWLEDGE_DIR

_DECISIONS_FILE = KNOWLEDGE_DIR / "org_decisions.json"


def _get_decisions_file(session_knowledge_dir: Optional[str] = None) -> Path:
    """Get the decisions file path, session-scoped if provided."""
    if session_knowledge_dir:
        p = Path(session_knowledge_dir) / "org_decisions.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    return _DECISIONS_FILE


def _read_all(session_knowledge_dir: Optional[str] = None) -> list[dict]:
    """Load all decisions from disk."""
    path = _get_decisions_file(session_knowledge_dir)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_all(decisions: list[dict], session_knowledge_dir: Optional[str] = None) -> None:
    """Persist the full decision list to disk."""
    path = _get_decisions_file(session_knowledge_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)


def list_decisions(session_knowledge_dir: Optional[str] = None) -> list[OrgDecision]:
    """Return all saved decisions as Pydantic models."""
    return [OrgDecision.model_validate(d) for d in _read_all(session_knowledge_dir)]


def add_decision(
    decision_type: str,
    source_term: str,
    mapped_term: str,
    description: str,
    author: str = "SME",
    session_knowledge_dir: Optional[str] = None,
) -> OrgDecision:
    """
    Create and persist a new organizational decision.

    Args:
        decision_type: One of 'terminology_clarification',
                       'business_rule', or 'reporting_preference'.
        source_term:   The original term from the CMS document.
        mapped_term:   The organization's preferred term or interpretation.
        description:   Free-text explanation of the decision.
        author:        Who is making this decision.
        session_knowledge_dir: Optional session-scoped knowledge directory.

    Returns:
        The newly created OrgDecision.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Initial change history entry
    initial_change = {
        "decision_id": "",  # Will be set below
        "author": author,
        "timestamp": now,
        "change": "Decision created",
        "previous_values": {},
    }

    decision = OrgDecision(
        decision_id=str(uuid.uuid4())[:8],
        type=decision_type,
        source_term=source_term,
        mapped_term=mapped_term,
        description=description,
        timestamp=now,
        author=author,
        version=1,
        change_history=[],
    )

    initial_change["decision_id"] = decision.decision_id
    decision.change_history.append(initial_change)

    decisions = _read_all(session_knowledge_dir)
    decisions.append(decision.model_dump())
    _write_all(decisions, session_knowledge_dir)

    return decision


def update_decision(
    decision_id: str,
    author: str = "SME",
    session_knowledge_dir: Optional[str] = None,
    **kwargs,
) -> OrgDecision | None:
    """
    Update fields of an existing decision by its ID.

    Records the previous values in change_history before overwriting.

    Returns the updated decision, or None if not found.
    """
    decisions = _read_all(session_knowledge_dir)
    now = datetime.now(timezone.utc).isoformat()

    for i, d in enumerate(decisions):
        if d["decision_id"] == decision_id:
            # Record change in history
            changed_fields = {k: v for k, v in kwargs.items() if k in d and k not in ("author", "session_knowledge_dir")}
            if changed_fields:
                change_entry = {
                    "decision_id": decision_id,
                    "author": author,
                    "timestamp": now,
                    "change": f"Updated {', '.join(changed_fields.keys())}",
                    "previous_values": {k: d[k] for k in changed_fields},
                }
                d.setdefault("change_history", []).append(change_entry)

            # Apply the changes
            for key, value in kwargs.items():
                if key in d and key not in ("author", "session_knowledge_dir"):
                    d[key] = value

            d["timestamp"] = now
            d["author"] = author
            d["version"] = d.get("version", 1) + 1

            decisions[i] = d
            _write_all(decisions, session_knowledge_dir)
            return OrgDecision.model_validate(d)

    return None


def delete_decision(
    decision_id: str,
    session_knowledge_dir: Optional[str] = None,
) -> bool:
    """
    Delete a decision by its ID.

    Returns True if a decision was deleted, False otherwise.
    """
    decisions = _read_all(session_knowledge_dir)
    filtered = [d for d in decisions if d["decision_id"] != decision_id]

    if len(filtered) == len(decisions):
        return False

    _write_all(filtered, session_knowledge_dir)
    return True


def get_decision_history(
    decision_id: str,
    session_knowledge_dir: Optional[str] = None,
) -> list[dict]:
    """
    Get the full change history for a decision.

    Returns a list of change entries (newest first).
    """
    decisions = _read_all(session_knowledge_dir)
    for d in decisions:
        if d["decision_id"] == decision_id:
            history = d.get("change_history", [])
            return sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)
    return []
