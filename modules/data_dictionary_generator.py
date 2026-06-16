"""
Data Dictionary Generator – creates the final source-to-report mapping
document that traces every report field back through the pipeline.

Uses Gemini to synthesize requirements, FHIR mappings, the analytics
model, reporting intents, and organizational decisions into a single
comprehensive data dictionary.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import DataDictionaryEntry, DataDictionarySet
from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_INTENT_FILE = OUTPUT_DIR / "reporting_intent.json"
_MAPPING_CACHE_FILE = KNOWLEDGE_DIR / "mapping_cache.json"
_DATA_DICTIONARY_FILE = OUTPUT_DIR / "data_dictionary.json"

# Valid enumerations
VALID_CLASSIFICATIONS = ["FHIR", "Derived", "Non-FHIR"]
VALID_SOURCE_TYPES = ["Direct", "Derived", "SME Rule"]
VALID_REPORT_USAGES = ["Table", "KPI", "Trend", "Matrix", "Export"]

_SYSTEM_INSTRUCTION = """\
You are a healthcare data governance specialist creating a comprehensive
data dictionary for a CMS reporting system.  You will receive:

1. CMS reporting requirements (metrics, dimensions, filters, business
   rules, exclusions).
2. FHIR-to-data mappings (concept → FHIR resource/field).
3. A star schema analytics model (fact/dimension tables and columns).
4. Reporting intent classifications (what visual each requirement maps to).
5. Organizational decisions from SME reviews.

Your task: produce a **data dictionary** — one entry per report field —
that traces each field from its source through transformations to its
final report usage.

For EACH report field produce:
- report_field: The field name as it appears in the report (use
  business-friendly names, e.g., "Organization Determination Number",
  not "od_number").
- business_definition: A clear, plain-language definition of what this
  field represents in the CMS reporting context.
- classification: Exactly one of:
    - **FHIR**: Field maps directly to a FHIR US Core resource field.
    - **Derived**: Field is computed or derived from one or more source
      fields (e.g., counts, ratios, date differences).
    - **Non-FHIR**: Field comes from a non-FHIR source (e.g., CMS
      reference tables, manual entry, organizational rules).
- source_type: Exactly one of:
    - **Direct**: Value is taken directly from a source field with no
      transformation.
    - **Derived**: Value is calculated from one or more source fields.
    - **SME Rule**: Value is determined by an organizational decision
      or SME-defined business rule.
- source_resource: The FHIR resource or star schema table this field
  originates from (e.g., "Patient", "FactObservation", "DimDate").
- source_field: The specific source column or FHIR field path (e.g.,
  "Patient.identifier", "FactObservation.disposition").
- transformation_rule: Description of any transformation applied.
  For direct fields use "None — direct mapping". For derived fields
  describe the calculation. For SME rules cite the organizational
  decision.
- report_usage: How this field is used in the final report. Exactly
  one of: **Table**, **KPI**, **Trend**, **Matrix**, **Export**.
  Choose based on the reporting intent classifications provided.

Rules:
- Include ALL data elements from the CMS requirements (every metric,
  dimension, filter field).
- Include ALL columns from the star schema fact tables that represent
  reportable data (skip surrogate keys).
- Include any derived metrics/KPIs from the analytics model.
- Apply organizational decisions when they affect field names or
  definitions.
- Use only the enumerated values for classification, source_type,
  and report_usage.
- Be thorough — a complete data dictionary should have 40+ entries
  for a comprehensive CMS report.
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


def _load_json_file(path: Path) -> dict | list | None:
    """Load a JSON file, returning None if missing."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_data_dictionary(
    requirements: dict,
    decisions: list[dict] | None = None,
) -> list[DataDictionaryEntry]:
    """
    Generate a comprehensive data dictionary from all upstream artifacts.

    Args:
        requirements: The extracted CMS requirements dict.
        decisions: Organizational decisions list (optional).

    Returns:
        A list of validated DataDictionaryEntry objects.
    """
    client = _get_client()

    analytics_model = _load_json_file(_ANALYTICS_MODEL_FILE)
    if not analytics_model:
        raise ValueError(
            "No analytics model found. Please generate and approve "
            "the analytics model on the Analytics Model page first."
        )

    mapping_cache = _load_json_file(_MAPPING_CACHE_FILE)
    reporting_intents = _load_json_file(_INTENT_FILE)

    # Build context
    context_parts = []

    context_parts.append(
        f"=== CMS REQUIREMENTS ===\n{json.dumps(requirements, indent=2)}"
    )

    context_parts.append(
        f"=== STAR SCHEMA ANALYTICS MODEL ===\n"
        f"{json.dumps(analytics_model, indent=2)}"
    )

    if mapping_cache:
        context_parts.append(
            f"=== FHIR MAPPING CACHE ===\n"
            f"{json.dumps(mapping_cache, indent=2)}"
        )

    if reporting_intents:
        context_parts.append(
            f"=== REPORTING INTENT CLASSIFICATIONS ===\n"
            f"{json.dumps(reporting_intents, indent=2)}"
        )

    if decisions:
        context_parts.append(
            f"=== ORGANIZATIONAL DECISIONS ===\n"
            f"{json.dumps(decisions, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=DataDictionarySet,
            temperature=0.2,
        ),
    )

    raw = json.loads(response.text)
    result = DataDictionarySet.model_validate(raw)
    return result.entries


def save_data_dictionary(entries: list[dict]) -> str:
    """Persist approved data dictionary to output/data_dictionary.json."""
    _DATA_DICTIONARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_DATA_DICTIONARY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    return str(_DATA_DICTIONARY_FILE.resolve())


def load_data_dictionary() -> list[dict] | None:
    """Load previously saved data dictionary."""
    if not _DATA_DICTIONARY_FILE.exists():
        return None
    with open(_DATA_DICTIONARY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
