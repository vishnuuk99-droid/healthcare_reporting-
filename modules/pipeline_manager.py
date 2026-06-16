"""
Pipeline Manager – strict sequential pipeline orchestration.

Tracks stage status (PENDING → IN_PROGRESS → COMPLETED → FAILED)
and enforces that each stage only runs when all prerequisites are met.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class StageStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Ordered pipeline stages with metadata
PIPELINE_STAGES = [
    {
        "id": "requirement_extraction",
        "label": "📄 Requirement Extraction",
        "prerequisites": [],
        "output_artifact": "requirements.json",
        "input_artifacts": [],
    },
    {
        "id": "frs_processing",
        "label": "📋 FRS Processing",
        "prerequisites": ["requirement_extraction"],
        "output_artifact": "frs_requirements.json",
        "input_artifacts": ["requirements.json"],
        "optional": True,
    },
    {
        "id": "requirement_merge",
        "label": "🔀 Requirement Merge",
        "prerequisites": ["requirement_extraction"],
        "output_artifact": "merged_requirements.json",
        "input_artifacts": ["requirements.json"],
    },
    {
        "id": "sme_review",
        "label": "💬 SME Review",
        "prerequisites": ["requirement_extraction"],
        "output_artifact": "org_decisions.json",
        "input_artifacts": ["requirements.json"],
    },
    {
        "id": "fhir_mapping",
        "label": "🔗 FHIR Mapping",
        "prerequisites": ["requirement_extraction"],
        "output_artifact": "mapping_cache.json",
        "input_artifacts": ["requirements.json"],
    },
    {
        "id": "analytics_model",
        "label": "📊 Analytics Model",
        "prerequisites": ["fhir_mapping"],
        "output_artifact": "analytics_model.json",
        "input_artifacts": ["requirements.json", "mapping_cache.json"],
    },
    {
        "id": "reporting_intent",
        "label": "🎯 Reporting Intent",
        "prerequisites": ["analytics_model"],
        "output_artifact": "reporting_intent.json",
        "input_artifacts": ["requirements.json", "analytics_model.json"],
    },
    {
        "id": "report_definition",
        "label": "📝 Report Definition",
        "prerequisites": ["analytics_model"],
        "output_artifact": "report_definition.json",
        "input_artifacts": ["requirements.json", "analytics_model.json"],
    },
    {
        "id": "data_dictionary",
        "label": "📖 Data Dictionary",
        "prerequisites": ["analytics_model"],
        "output_artifact": "data_dictionary.json",
        "input_artifacts": ["requirements.json", "analytics_model.json"],
    },
    {
        "id": "measures",
        "label": "📐 Measures",
        "prerequisites": ["report_definition", "analytics_model"],
        "output_artifact": "measures.json",
        "input_artifacts": ["report_definition.json", "analytics_model.json"],
    },
    {
        "id": "dax_generation",
        "label": "🔢 DAX Generation",
        "prerequisites": ["measures"],
        "output_artifact": "dax_artifacts.json",
        "input_artifacts": ["measures.json", "analytics_model.json"],
    },
    {
        "id": "pbip_generation",
        "label": "📦 PBIP Generation",
        "prerequisites": ["dax_generation", "report_definition"],
        "output_artifact": "pbip_project.zip",
        "input_artifacts": [
            "analytics_model.json",
            "report_definition.json",
            "dax_artifacts.json",
            "measures.json",
        ],
    },
]

# Quick lookup by stage id
_STAGE_MAP = {s["id"]: s for s in PIPELINE_STAGES}


class PipelineState:
    """
    Manages the execution state of all pipeline stages.

    Persists state to a JSON file so it survives Streamlit reruns.
    """

    def __init__(self, state_file: Optional[Path] = None):
        self._state_file = state_file
        self._stages: dict[str, dict] = {}
        self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self):
        """Load state from disk or initialise fresh."""
        if self._state_file and self._state_file.exists():
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._stages = data.get("stages", {})
            except Exception:
                self._stages = {}

        # Ensure every known stage has an entry
        for stage_def in PIPELINE_STAGES:
            sid = stage_def["id"]
            if sid not in self._stages:
                self._stages[sid] = {
                    "status": StageStatus.PENDING.value,
                    "started_at": None,
                    "completed_at": None,
                    "error": None,
                    "artifact_path": None,
                }

    def _save(self):
        """Persist current state to disk."""
        if not self._state_file:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump({"stages": self._stages}, f, indent=2, ensure_ascii=False)

    # ── Status Queries ──────────────────────────────────────────────

    def get_status(self, stage_id: str) -> StageStatus:
        entry = self._stages.get(stage_id, {})
        return StageStatus(entry.get("status", StageStatus.PENDING.value))

    def is_completed(self, stage_id: str) -> bool:
        return self.get_status(stage_id) == StageStatus.COMPLETED

    def can_run(self, stage_id: str) -> bool:
        """Check if all prerequisites of *stage_id* are COMPLETED."""
        stage_def = _STAGE_MAP.get(stage_id)
        if not stage_def:
            return False
        for prereq in stage_def.get("prerequisites", []):
            prereq_def = _STAGE_MAP.get(prereq, {})
            # Optional prerequisites don't block
            if prereq_def.get("optional"):
                continue
            if not self.is_completed(prereq):
                return False
        return True

    def get_missing_prerequisites(self, stage_id: str) -> list[str]:
        """Return list of prerequisite stage IDs that are not yet completed."""
        stage_def = _STAGE_MAP.get(stage_id, {})
        missing = []
        for prereq in stage_def.get("prerequisites", []):
            prereq_def = _STAGE_MAP.get(prereq, {})
            if prereq_def.get("optional"):
                continue
            if not self.is_completed(prereq):
                missing.append(prereq)
        return missing

    def get_stage_info(self, stage_id: str) -> dict:
        """Return the full state dict for a stage."""
        return self._stages.get(stage_id, {}).copy()

    def get_all_stages(self) -> list[dict]:
        """Return ordered list of stage states with definitions."""
        result = []
        for stage_def in PIPELINE_STAGES:
            sid = stage_def["id"]
            entry = self._stages.get(sid, {})
            result.append({
                "id": sid,
                "label": stage_def["label"],
                "status": entry.get("status", StageStatus.PENDING.value),
                "started_at": entry.get("started_at"),
                "completed_at": entry.get("completed_at"),
                "error": entry.get("error"),
                "optional": stage_def.get("optional", False),
            })
        return result

    # ── State Transitions ───────────────────────────────────────────

    def mark_started(self, stage_id: str):
        """Mark a stage as IN_PROGRESS."""
        if stage_id in self._stages:
            self._stages[stage_id]["status"] = StageStatus.IN_PROGRESS.value
            self._stages[stage_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            self._stages[stage_id]["error"] = None
            self._save()

    def mark_completed(self, stage_id: str, artifact_path: Optional[str] = None):
        """Mark a stage as COMPLETED."""
        if stage_id in self._stages:
            self._stages[stage_id]["status"] = StageStatus.COMPLETED.value
            self._stages[stage_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._stages[stage_id]["artifact_path"] = artifact_path
            self._stages[stage_id]["error"] = None
            self._save()

    def mark_failed(self, stage_id: str, error: str):
        """Mark a stage as FAILED with an error message."""
        if stage_id in self._stages:
            self._stages[stage_id]["status"] = StageStatus.FAILED.value
            self._stages[stage_id]["error"] = error
            self._save()

    def reset_stage(self, stage_id: str):
        """Reset a stage back to PENDING (unlock for re-generation)."""
        if stage_id in self._stages:
            self._stages[stage_id]["status"] = StageStatus.PENDING.value
            self._stages[stage_id]["started_at"] = None
            self._stages[stage_id]["completed_at"] = None
            self._stages[stage_id]["error"] = None
            self._stages[stage_id]["artifact_path"] = None
            self._save()

    def reset_downstream(self, stage_id: str):
        """Reset all stages that depend (directly or transitively) on *stage_id*."""
        dependents = self._find_dependents(stage_id)
        for dep_id in dependents:
            self.reset_stage(dep_id)

    def reset_all(self):
        """Reset every stage back to PENDING."""
        for sid in self._stages:
            self.reset_stage(sid)

    # ── Internal helpers ────────────────────────────────────────────

    def _find_dependents(self, stage_id: str) -> list[str]:
        """Find all stages that depend on *stage_id* (BFS)."""
        dependents = []
        queue = [stage_id]
        visited = {stage_id}
        while queue:
            current = queue.pop(0)
            for stage_def in PIPELINE_STAGES:
                sid = stage_def["id"]
                if sid in visited:
                    continue
                if current in stage_def.get("prerequisites", []):
                    dependents.append(sid)
                    visited.add(sid)
                    queue.append(sid)
        return dependents
