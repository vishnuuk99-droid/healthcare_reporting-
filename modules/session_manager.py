"""
Session Manager – project-level session isolation.

Every uploaded CMS document creates a completely new project session
with an isolated workspace.  No cross-report contamination.
"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from modules.file_manager import PROJECT_ROOT

PROJECTS_DIR = PROJECT_ROOT / "projects"


def _ensure_projects_dir():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def create_project_session(
    report_name: str,
    source_pdf: str = "",
) -> dict:
    """
    Create a new isolated project workspace.

    Returns a dict with session metadata including paths.
    """
    _ensure_projects_dir()

    report_id = str(uuid.uuid4())[:12]
    timestamp = datetime.now(timezone.utc).isoformat()
    project_dir = PROJECTS_DIR / report_id

    # Create sub-directories
    subdirs = [
        "requirements",
        "mappings",
        "analytics",
        "measures",
        "dax",
        "reports",
        "pbip",
        "knowledge",
    ]
    for sd in subdirs:
        (project_dir / sd).mkdir(parents=True, exist_ok=True)

    # Create output directory (mirrors flat output/ structure for compat)
    output_dir = project_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Session metadata
    meta = {
        "report_id": report_id,
        "report_name": report_name,
        "source_pdf": source_pdf,
        "created_at": timestamp,
        "last_accessed": timestamp,
    }
    meta_path = project_dir / "session_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    return {
        "report_id": report_id,
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "knowledge_dir": str(project_dir / "knowledge"),
        "meta": meta,
    }


def list_project_sessions() -> list[dict]:
    """Return all project sessions with metadata, sorted newest first."""
    _ensure_projects_dir()
    sessions = []

    for entry in PROJECTS_DIR.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "session_meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                meta["project_dir"] = str(entry)
                meta["output_dir"] = str(entry / "output")
                meta["knowledge_dir"] = str(entry / "knowledge")
                sessions.append(meta)
            except Exception:
                continue

    sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return sessions


def load_project_session(report_id: str) -> Optional[dict]:
    """Load a specific project session by ID."""
    project_dir = PROJECTS_DIR / report_id
    meta_path = project_dir / "session_meta.json"

    if not meta_path.exists():
        return None

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        # Update last accessed
        meta["last_accessed"] = datetime.now(timezone.utc).isoformat()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        return {
            "report_id": report_id,
            "project_dir": str(project_dir),
            "output_dir": str(project_dir / "output"),
            "knowledge_dir": str(project_dir / "knowledge"),
            "meta": meta,
        }
    except Exception:
        return None


def delete_project_session(report_id: str) -> bool:
    """Delete a project session and all its artifacts."""
    project_dir = PROJECTS_DIR / report_id
    if project_dir.exists():
        shutil.rmtree(project_dir)
        return True
    return False


def get_session_output_dir(report_id: str) -> Path:
    """Get the output directory for a session."""
    return PROJECTS_DIR / report_id / "output"


def get_session_knowledge_dir(report_id: str) -> Path:
    """Get the knowledge directory for a session."""
    return PROJECTS_DIR / report_id / "knowledge"


def get_session_pipeline_state_path(report_id: str) -> Path:
    """Get the pipeline state file path for a session."""
    return PROJECTS_DIR / report_id / "pipeline_state.json"


# ── Session-State Helpers (for Streamlit integration) ────────────────

def clear_session_state_for_new_report(st_session_state):
    """
    Clear all report-related keys from Streamlit session state.
    Called when a new report is uploaded to prevent contamination.
    """
    keys_to_clear = [
        # Extracted data
        "extracted_text",
        "requirements_json",
        "frs_text",
        "frs_requirements",
        "merged_requirements",
        # Stage outputs
        "fhir_mappings",
        "analytics_model",
        "analytics_model_approved",
        "reporting_intents",
        "intents_approved",
        "report_definition",
        "report_approved",
        "data_dictionary",
        "dd_approved",
        "measures",
        "measures_approved",
        "dax_measures",
        "dax_approved",
        "pbip_results",
        # SME state
        "sme_messages",
        # Validator state
        "enforcer_applied_fixes",
        "report_layout_applied_fixes",
    ]

    for key in keys_to_clear:
        if key in st_session_state:
            del st_session_state[key]

    # Also clear any editing/overriding state keys
    keys_to_remove = [
        k for k in st_session_state
        if k.startswith(("editing_", "overriding_"))
    ]
    for key in keys_to_remove:
        del st_session_state[key]
