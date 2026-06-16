"""
Requirement Merger – combines CMS and FRS requirements into a unified
model.  Detects conflicts and routes them to the SME workspace.

Priority chain:  CMS Requirements → FRS Clarifications → SME Decisions
"""

import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import MergedRequirementModel, MergeConflict

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


_MERGE_SYSTEM_INSTRUCTION = """\
You are a healthcare requirements analyst AI.  You are given two sets of
requirements for the same Power BI report:

1. **CMS Requirements** – extracted directly from the CMS regulatory
   document.  These are authoritative and take priority.
2. **FRS Requirements** – extracted from a Functional Requirements
   Specification written by the business team.  These provide
   clarifications, additional KPIs, and visualisation preferences.

Your job is to merge these into a single unified model:

- merged_metrics: Combine all unique metrics from both sources.
  CMS metrics always take priority if there is overlap.
- merged_dimensions: Combine all unique dimensions.
- merged_filters: Combine all unique filters.
- merged_business_rules: Combine all unique business rules.
- conflicts: Identify any conflicts between CMS and FRS where:
    - The same metric/KPI has different definitions (definition_mismatch)
    - A metric exists in FRS but not in CMS (missing_in_cms)
    - A metric exists in CMS but not in FRS (missing_in_frs)
  For each conflict provide: field, cms_value, frs_value, conflict_type.
  Do NOT set resolved=true — that is for the SME to decide.
- assumptions: List any assumptions you made during the merge as
  [{"assumption": "...", "reason": "..."}].

Return JSON conforming to the MergedRequirementModel schema.
"""


def _get_client() -> genai.Client:
    """Create and return a configured Gemini client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY not found. "
            "Create a .env file in the project root with:\n"
            "GEMINI_API_KEY=your_key_here"
        )
    return genai.Client(api_key=api_key)


def merge_requirements(
    cms_req: dict,
    frs_req: Optional[dict] = None,
) -> MergedRequirementModel:
    """
    Merge CMS and FRS requirements into a unified model.

    If frs_req is None, returns a model with CMS requirements only
    (no merge needed, no conflicts).

    Args:
        cms_req: Dictionary of CMS requirements (from requirements.json).
        frs_req: Dictionary of FRS requirements (from frs_requirements.json).
                 Optional — if not provided, CMS requirements are used as-is.

    Returns:
        A MergedRequirementModel with unified requirements and any conflicts.
    """
    if not frs_req:
        # No FRS — just wrap CMS requirements
        return MergedRequirementModel(
            cms_requirements=cms_req,
            frs_requirements={},
            merged_metrics=cms_req.get("metrics", []),
            merged_dimensions=cms_req.get("dimensions", []),
            merged_filters=cms_req.get("filters", []),
            merged_business_rules=cms_req.get("business_rules", []),
            conflicts=[],
            assumptions=[{"assumption": "No FRS provided", "reason": "CMS requirements used as-is."}],
        )

    # Build the prompt
    prompt = (
        "## CMS Requirements\n"
        f"```json\n{json.dumps(cms_req, indent=2)}\n```\n\n"
        "## FRS Requirements\n"
        f"```json\n{json.dumps(frs_req, indent=2)}\n```\n\n"
        "Merge these two requirement sets following the instructions."
    )

    client = _get_client()

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_MERGE_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=MergedRequirementModel,
            temperature=0.2,
        ),
    )

    raw_json = json.loads(response.text)
    merged = MergedRequirementModel.model_validate(raw_json)

    # Ensure original requirements are preserved
    merged.cms_requirements = cms_req
    merged.frs_requirements = frs_req

    return merged


def get_unresolved_conflicts(merged: MergedRequirementModel) -> list[MergeConflict]:
    """Return only the unresolved conflicts from a merged model."""
    return [c for c in merged.conflicts if not c.resolved]


def resolve_conflict(
    merged: MergedRequirementModel,
    field: str,
    resolution: str,
) -> MergedRequirementModel:
    """
    Mark a conflict as resolved with the given resolution text.

    Returns the updated model.
    """
    for conflict in merged.conflicts:
        if conflict.field == field and not conflict.resolved:
            conflict.resolution = resolution
            conflict.resolved = True
            break
    return merged


def save_merged_requirements(
    merged: MergedRequirementModel,
    output_path: str | Path,
) -> str:
    """Persist merged requirements to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(merged.model_dump_json(indent=2))

    # Also save the flat conformed requirements for downstream stages
    conformed = merged.cms_requirements.copy() if merged.cms_requirements else {}
    conformed["metrics"] = merged.merged_metrics
    conformed["dimensions"] = merged.merged_dimensions
    conformed["filters"] = merged.merged_filters
    conformed["business_rules"] = merged.merged_business_rules

    conformed_path = output_path.parent / "conformed_requirements.json"
    with open(conformed_path, "w", encoding="utf-8") as f:
        json.dump(conformed, f, indent=2, ensure_ascii=False)

    return str(output_path.resolve())


def load_merged_requirements(output_dir: str | Path) -> Optional[MergedRequirementModel]:
    """Load previously saved merged requirements from disk."""
    path = Path(output_dir) / "merged_requirements.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MergedRequirementModel.model_validate(data)
    except Exception:
        return None
