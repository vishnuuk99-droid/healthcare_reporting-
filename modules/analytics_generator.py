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
- Include surrogate key columns (e.g., patient_key, provider_key, date_key).
- Include date dimension foreign keys where applicable.
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

    raw = json.loads(response.text)
    return AnalyticsModel.model_validate(raw)


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
