"""
Decision store – CRUD operations for organizational SME decisions.

Persists decisions to knowledge/org_decisions.json and provides
helpers for listing, updating, and deleting entries.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modules.schemas import OrgDecision
from modules.file_manager import KNOWLEDGE_DIR

_DECISIONS_FILE = KNOWLEDGE_DIR / "org_decisions.json"


def _read_all() -> list[dict]:
    """Load all decisions from disk."""
    if not _DECISIONS_FILE.exists():
        return []
    with open(_DECISIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_all(decisions: list[dict]) -> None:
    """Persist the full decision list to disk."""
    _DECISIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_DECISIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)


def list_decisions() -> list[OrgDecision]:
    """Return all saved decisions as Pydantic models."""
    return [OrgDecision.model_validate(d) for d in _read_all()]


def add_decision(
    decision_type: str,
    source_term: str,
    mapped_term: str,
    description: str,
) -> OrgDecision:
    """
    Create and persist a new organizational decision.

    Args:
        decision_type: One of 'terminology_clarification',
                       'business_rule', or 'reporting_preference'.
        source_term:   The original term from the CMS document.
        mapped_term:   The organization's preferred term or interpretation.
        description:   Free-text explanation of the decision.

    Returns:
        The newly created OrgDecision.
    """
    decision = OrgDecision(
        decision_id=str(uuid.uuid4())[:8],
        type=decision_type,
        source_term=source_term,
        mapped_term=mapped_term,
        description=description,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    decisions = _read_all()
    decisions.append(decision.model_dump())
    _write_all(decisions)

    return decision


def update_decision(decision_id: str, **kwargs) -> OrgDecision | None:
    """
    Update fields of an existing decision by its ID.

    Returns the updated decision, or None if not found.
    """
    decisions = _read_all()

    for i, d in enumerate(decisions):
        if d["decision_id"] == decision_id:
            for key, value in kwargs.items():
                if key in d:
                    d[key] = value
            d["timestamp"] = datetime.now(timezone.utc).isoformat()
            decisions[i] = d
            _write_all(decisions)
            return OrgDecision.model_validate(d)

    return None


def delete_decision(decision_id: str) -> bool:
    """
    Delete a decision by its ID.

    Returns True if a decision was deleted, False otherwise.
    """
    decisions = _read_all()
    filtered = [d for d in decisions if d["decision_id"] != decision_id]

    if len(filtered) == len(decisions):
        return False

    _write_all(filtered)
    return True
