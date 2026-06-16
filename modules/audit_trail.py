"""
Audit Trail – logs every artifact generation with full traceability.

Records which inputs were consumed, which SME decisions were applied,
and the output artifact produced at each pipeline stage.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _get_audit_path(project_dir: Optional[str] = None) -> Path:
    """Get the audit log file path."""
    if project_dir:
        return Path(project_dir) / "audit_log.json"
    from modules.file_manager import OUTPUT_DIR
    return OUTPUT_DIR / "audit_log.json"


def _read_log(project_dir: Optional[str] = None) -> list[dict]:
    """Read the existing audit log."""
    path = _get_audit_path(project_dir)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _write_log(entries: list[dict], project_dir: Optional[str] = None):
    """Write the audit log to disk."""
    path = _get_audit_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def log_artifact_generation(
    stage: str,
    artifact_path: str,
    inputs_used: list[str],
    sme_decisions_applied: Optional[list[str]] = None,
    status: str = "COMPLETED",
    notes: str = "",
    project_dir: Optional[str] = None,
) -> dict:
    """
    Log a pipeline stage execution to the audit trail.

    Args:
        stage: Pipeline stage ID (e.g., 'fhir_mapping').
        artifact_path: Path to the produced artifact.
        inputs_used: List of input file paths consumed.
        sme_decisions_applied: List of decision IDs applied (if any).
        status: Stage result status.
        notes: Optional notes about the execution.
        project_dir: Optional project directory for session-scoped audit.

    Returns:
        The audit entry dict.
    """
    entry = {
        "stage": stage,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "artifact": artifact_path,
        "inputs": inputs_used,
        "sme_decisions": sme_decisions_applied or [],
        "status": status,
        "notes": notes,
    }

    entries = _read_log(project_dir)
    entries.append(entry)
    _write_log(entries, project_dir)

    return entry


def get_audit_log(project_dir: Optional[str] = None) -> list[dict]:
    """Get the full audit log, newest entries first."""
    entries = _read_log(project_dir)
    return sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)


def get_stage_audit(
    stage: str,
    project_dir: Optional[str] = None,
) -> list[dict]:
    """Get audit entries for a specific stage."""
    entries = _read_log(project_dir)
    return [e for e in entries if e["stage"] == stage]


def get_artifact_lineage(
    artifact_path: str,
    project_dir: Optional[str] = None,
) -> dict:
    """
    Trace the full lineage of an artifact back through the pipeline.

    Returns a dict with the artifact's generation entry and all upstream
    inputs recursively.
    """
    entries = _read_log(project_dir)

    # Find the entry that produced this artifact
    production_entry = None
    for e in reversed(entries):
        if e["artifact"] == artifact_path:
            production_entry = e
            break

    if not production_entry:
        return {"artifact": artifact_path, "lineage": [], "not_found": True}

    lineage = [production_entry]

    # Recursively trace inputs
    for input_path in production_entry.get("inputs", []):
        upstream = get_artifact_lineage(input_path, project_dir)
        if not upstream.get("not_found"):
            lineage.extend(upstream.get("lineage", []))

    return {
        "artifact": artifact_path,
        "lineage": lineage,
    }
