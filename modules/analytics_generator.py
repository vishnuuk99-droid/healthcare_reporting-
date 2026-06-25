"""
Analytics Model Generator – produces star schema metadata from FHIR mappings.

Uses Gemini to transform approved CMS-to-FHIR mappings into an
analytics-ready star schema with fact tables, dimension tables,
relationships, metrics, and drill-down attributes.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import AnalyticsModel
from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_MAPPING_CACHE_FILE = KNOWLEDGE_DIR / "mapping_cache.json"
_ANALYTICS_OUTPUT = OUTPUT_DIR / "analytics_model.json"

# FHIR resource → star schema table name mapping rules (kept for description/UI compat)
FHIR_TO_STAR = {
    "Patient": "DimPatient (or DimMember)",
    "Practitioner": "DimProvider",
    "Organization": "DimOrganization",
    "Condition": "DimCondition",
    "Encounter": "FactEncounter / FactAdmissionNotification",
    "Observation": "FactOrganizationDetermination / FactGrievance / FactSupplementalBenefit",
    "Procedure": "FactProcedure",
    "MedicationRequest": "FactMedication",
}

_SYSTEM_INSTRUCTION = """\
You are a healthcare data warehouse architect. Your job is to generate
an analytics-ready star schema model from CMS reporting requirements,
incorporating organizational decisions.

CMS business terminology MUST always take precedence over FHIR terminology.
Do not convert CMS concepts into generic healthcare concepts. The goal is to
build reports based on CMS language, not based on FHIR resource names.

Generate analytics models from CMS business entities.
You MUST generate separate fact tables for each distinct CMS business concept.
Examples of fact tables to generate:
- FactOrganizationDetermination (NOT FactObservation)
- FactAppeal (NOT FactObservation)
- FactGrievance (NOT FactObservation)
- FactEnrollment (NOT FactObservation)
- FactProviderPayment (NOT FactObservation)
- FactSupplementalBenefit (NOT FactProcedure)
- FactSNP_CareManagement (NOT FactObservation)
- FactAdmissionNotification (NOT FactEncounter)
(Or other explicit CMS business entities described in the requirements).

Do NOT create generic healthcare/FHIR tables like:
- FactObservation
- FactClinicalEvent
- FactFHIRResource
- FactEncounter
- FactProcedure
- FactMedication
under any circumstances. Instead, split these events into their respective CMS business entity fact tables (e.g. FactGrievance, FactAppeal, FactOrganizationDetermination).

Dimensions (e.g., DimPatient, DimProvider, DimOrganization, DimDate, DimCondition) should be generated only when required by the business requirements.

For each fact and dimension table, populate the columns' source_fhir_resource and source_fhir_field using general FHIR knowledge as supporting metadata/traceability only.

Generate a complete star schema model conforming to the response schema:

**fact_tables**: Each fact table must have:
  - name: The star schema table name (e.g., FactOrganizationDetermination)
  - source_fhir_resource: The FHIR resource it derives from (optional metadata, e.g., Observation)
  - description: Business purpose of this fact table
  - grain: What one row represents
  - columns: List of column objects with {name, data_type, source_fhir_field, description}

**dimension_tables**: Each dimension table must have:
  - name: The star schema table name (e.g., DimPatient)
  - source_fhir_resource: The FHIR resource it derives from (optional metadata)
  - description: Business purpose
  - columns: List of column objects with {name, data_type, source_fhir_field, description}

**relationships**: Foreign key relationships:
  - fact_table: Name of the fact table
  - dimension_table: Name of the dimension table
  - join_key: The foreign key column name
  - relationship_type: "many-to-one" or "many-to-many"

**metrics**: Business metrics that can be computed:
  - name: Metric name (e.g., "total_grievances")
  - description: Business definition
  - formula: SQL-like formula or calculation logic
  - fact_table: Which fact table it comes from
  - dimensions: Which dimensions it can be sliced by

**attributes**: Drill-down attributes:
  - name: Attribute name
  - table: Which table it belongs to
  - drill_path: Ordered list showing drill-down hierarchy
  - description: What this attribute represents

Rules:
- Include surrogate key columns (e.g., patient_key, provider_key, date_key, organization_key).
- Include `organization_key` in all primary fact tables, linked to `DimOrganization`.
- Include `calendar_month` in the `DimDate` table and `plan_name` in the `DimOrganization` table.
- Include date dimension foreign keys where applicable.
- Prevent circular active relationships: If multiple fact tables link to `DimDate` but are also linked to each other (e.g. `FactPriorAuthorization` and `FactAppeal`), set `is_active: false` on the secondary fact table's date relationship to avoid multiple active filtering paths.
- Include degenerate dimensions in fact tables where appropriate.
- Add a DimDate dimension table for time-based analysis.
- Metrics should reflect the CMS requirements' metrics list.
- Apply organizational decisions — use mapped terms, not source terms.
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


def _load_mapping_cache() -> list[dict]:
    """Load approved FHIR mappings."""
    if not _MAPPING_CACHE_FILE.exists():
        return []
    with open(_MAPPING_CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_analytics_model(
    requirements: dict,
    decisions: list[dict] | None = None,
) -> AnalyticsModel:
    """
    Generate a star schema analytics model from conformed requirements and decisions.

    Args:
        requirements: The extracted CMS requirements dict.
        decisions: Organizational decisions list (optional).

    Returns:
        A validated AnalyticsModel instance.
    """
    client = _get_client()

    # Build context
    context_parts = []

    context_parts.append(
        f"=== CMS REQUIREMENTS ===\n{json.dumps(requirements, indent=2)}"
    )

    structured_metrics = requirements.get("structured_metrics", [])
    if structured_metrics:
        context_parts.append(
            f"=== STRUCTURED METRIC DEFINITIONS ===\n"
            f"Use these to design fact tables. Each metric's numerator/denominator "
            f"describes what the fact table must capture. Group metrics by CMS "
            f"business concept to determine fact tables.\n"
            f"{json.dumps(structured_metrics, indent=2)}"
        )

    if decisions:
        context_parts.append(
            f"=== ORGANIZATIONAL DECISIONS ===\n{json.dumps(decisions, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=AnalyticsModel,
            temperature=0.2,
        ),
    )

    raw_json = json.loads(response.text)
    
    structured_metrics = requirements.get("structured_metrics", [])
    quality_report = validate_analytics_quality(raw_json, structured_metrics)
    
    # Store quality metadata in the model
    raw_json["_quality_report"] = quality_report

    if quality_report["analytics_quality_score"] < 70.0:
        raise ValueError(
            f"Analytics model quality score too low "
            f"({quality_report['analytics_quality_score']}%). "
            f"Generic fact tables detected: {quality_report['generic_fact_tables']}. "
            f"Affected metrics: {quality_report['affected_metrics']}. "
            f"Re-run analytics model generation with CMS-specific tables."
        )

    return AnalyticsModel.model_validate(raw_json)


_BANNED_FACT_NAMES = {"FactObservation", "FactClinicalEvent", "FactFHIRResource"}

def validate_analytics_quality(model_data: dict, structured_metrics: list[dict]) -> dict:
    """
    Post-LLM analytics model quality validation (Enhancement 3).

    Returns:
        dict with analytics_quality_score, generic_fact_tables, affected_metrics,
        and _validation_warnings list.
    """
    fact_names = {f.get("name", "") for f in model_data.get("fact_tables", [])}
    generic_facts = fact_names.intersection(_BANNED_FACT_NAMES)
    total_facts = len(fact_names)

    # Determine which metrics would be affected by generic tables
    affected_metrics = []
    model_metrics = model_data.get("metrics", [])
    for m in model_metrics:
        if m.get("fact_table", "") in generic_facts:
            affected_metrics.append(m.get("name", ""))

    # Also check structured metrics whose concepts map to generic tables
    for sm in structured_metrics:
        metric_name = sm.get("metric_name", "")
        if metric_name not in affected_metrics:
            covered = False
            for m in model_metrics:
                if m.get("name", "") == metric_name and m.get("fact_table", "") not in generic_facts:
                    covered = True
                    break
            if not covered and generic_facts:
                affected_metrics.append(metric_name)

    # Score: 100% if no generic facts, reduced proportionally
    if total_facts > 0:
        quality_score = round((1.0 - len(generic_facts) / total_facts) * 100, 1)
    else:
        quality_score = 0.0

    warnings = []
    for gf in generic_facts:
        warnings.append(
            f"Generic fact table '{gf}' detected. CMS reporting requires "
            f"business-specific tables (e.g., FactGrievance, FactOrganizationDetermination)."
        )

    return {
        "analytics_quality_score": quality_score,
        "generic_fact_tables": list(generic_facts),
        "affected_metrics": affected_metrics,
        "_validation_warnings": warnings,
    }


def save_analytics_model(model: AnalyticsModel) -> str:
    """Persist the analytics model to output/analytics_model.json."""
    _ANALYTICS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_ANALYTICS_OUTPUT, "w", encoding="utf-8") as f:
        f.write(model.model_dump_json(indent=2))
    return str(_ANALYTICS_OUTPUT.resolve())


def load_analytics_model() -> dict | None:
    """Load a previously saved analytics model."""
    if not _ANALYTICS_OUTPUT.exists():
        return None
    with open(_ANALYTICS_OUTPUT, "r", encoding="utf-8") as f:
        return json.load(f)
