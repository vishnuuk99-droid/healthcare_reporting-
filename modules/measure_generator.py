"""
Measure Generator – creates business measures from the approved report
definition, data dictionary, analytics model, and reporting intents.

Uses Gemini to generate comprehensive business measures with formulas,
source lineage, dependency chains, and classifications needed for
Power BI DAX implementation.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import MeasureEntry, MeasureSet
from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_REPORT_DEFINITION_FILE = OUTPUT_DIR / "report_definition.json"
_DATA_DICTIONARY_FILE = OUTPUT_DIR / "data_dictionary.json"
_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_INTENT_FILE = OUTPUT_DIR / "reporting_intent.json"
_REQUIREMENTS_FILE = OUTPUT_DIR / "requirements.json"
_DECISIONS_FILE = KNOWLEDGE_DIR / "org_decisions.json"
_MEASURES_FILE = OUTPUT_DIR / "measures.json"

# Valid enumerations
VALID_MEASURE_TYPES = [
    "Count", "Sum", "Average", "Percentage",
    "Ratio", "Distinct Count", "Trend",
]
VALID_CLASSIFICATIONS = ["Base Measure", "Derived Measure", "KPI"]

_SYSTEM_INSTRUCTION = """\
You are a Power BI measure architect specialising in CMS healthcare
analytics.  You will receive:

1. A Power BI report definition (pages, visuals, DAX measures, filters).
2. A data dictionary mapping report fields to source fields.
3. A star schema analytics model with fact/dimension tables, columns,
   metrics, and attributes.
4. Reporting intent classifications for CMS requirements.
5. The raw CMS requirements.
6. Organizational decisions from SME reviews.

Your task: generate a comprehensive set of **business measures** that
cover every metric needed by the report visuals, KPI cards, trend
analyses, and data exports.

For EACH measure produce:
- measure_name: A business-friendly name (e.g., "Total Organization
  Determinations", "Adverse Decision Rate", "Quarterly Volume Trend").
- business_definition: Clear explanation of what this measure represents
  and why it matters for CMS reporting.
- measure_type: Exactly one of:
    - **Count**: Counts of records/rows
    - **Sum**: Summation of numeric values
    - **Average**: Mean of numeric values
    - **Percentage**: A proportion expressed as percentage
    - **Ratio**: A ratio between two quantities
    - **Distinct Count**: Count of unique values
    - **Trend**: A time-series or period-over-period calculation
- formula_description: Human-readable description of the formula logic.
  Include the DAX expression or pseudo-formula. For example:
  "COUNTROWS(FILTER(FactObservation, disposition = 'Adverse'))"
- source_fields: List of star schema column names consumed by this
  measure (e.g., ["od_number", "disposition", "date_of_decision_key"]).
- source_tables: List of star schema tables this measure draws from
  (e.g., ["FactObservation", "DimDate"]).
- classification: Exactly one of:
    - **Base Measure**: A foundational measure that does not depend on
      other measures (e.g., total count, sum).
    - **Derived Measure**: A measure computed from one or more base
      measures (e.g., rate = adverse / total).
    - **KPI**: A key performance indicator with a target or threshold
      (e.g., timeliness rate, compliance percentage).
- dependencies: List of names of other measures that this measure depends on.
  For Base Measures, this must be an empty list []. For Derived Measures
  or KPIs, list the exact measure names that are used in its calculation
  (e.g. if Adverse Rate = Adverse Decisions / Total Decisions, it depends on
  ["Total Adverse Decisions", "Total Decisions"]).
- report_pages: List of names of report pages (from the report definition)
  where this measure is used in a visual.
- visuals_used_in: List of titles of report visuals (from the report definition)
  where this measure is used.

Rules:
- Generate measures for EVERY visual in the report definition that
  references a measure or DAX expression.
- Include base measures that derived measures depend on.
- Create KPI measures for executive summary / dashboard cards.
- Include trend measures for time-series visuals (period-over-period).
- Reference ONLY columns and tables present in the analytics model.
- Use the data dictionary to ensure business-friendly naming.
- Apply reporting intents to determine measure purpose (KPI vs Table).
- Order measures: Base Measures first, then Derived, then KPIs.
- Be thorough — a comprehensive CMS report needs 20+ measures.
- Show dependency chains: if "Adverse Rate" depends on "Total Adverse"
  and "Total Decisions", generate all three and specify dependencies correctly.
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


def generate_measures(
    decisions: list[dict] | None = None,
) -> list[MeasureEntry]:
    """
    Generate business measures from all upstream artifacts.

    Args:
        decisions: Organizational decisions list (optional).

    Returns:
        A list of validated MeasureEntry objects.
    """
    client = _get_client()

    report_definition = _load_json_file(_REPORT_DEFINITION_FILE)
    if not report_definition:
        raise ValueError(
            "No report definition found. Please generate and approve "
            "the report on the Report Definition page first."
        )

    analytics_model = _load_json_file(_ANALYTICS_MODEL_FILE)
    if not analytics_model:
        raise ValueError(
            "No analytics model found. Please generate and approve "
            "the model on the Analytics Model page first."
        )

    data_dictionary = _load_json_file(_DATA_DICTIONARY_FILE)
    reporting_intents = _load_json_file(_INTENT_FILE)
    requirements = _load_json_file(_REQUIREMENTS_FILE)
    
    if not decisions:
        decisions = _load_json_file(_DECISIONS_FILE) or []

    # Build context
    context_parts = []

    context_parts.append(
        f"=== REPORT DEFINITION ===\n"
        f"{json.dumps(report_definition, indent=2)}"
    )

    context_parts.append(
        f"=== STAR SCHEMA ANALYTICS MODEL ===\n"
        f"{json.dumps(analytics_model, indent=2)}"
    )

    if data_dictionary:
        context_parts.append(
            f"=== DATA DICTIONARY ===\n"
            f"{json.dumps(data_dictionary, indent=2)}"
        )

    if reporting_intents:
        context_parts.append(
            f"=== REPORTING INTENT CLASSIFICATIONS ===\n"
            f"{json.dumps(reporting_intents, indent=2)}"
        )

    if requirements:
        context_parts.append(
            f"=== CMS REQUIREMENTS ===\n"
            f"{json.dumps(requirements, indent=2)}"
        )

    if decisions:
        context_parts.append(
            f"=== ORGANIZATIONAL DECISIONS ===\n"
            f"{json.dumps(decisions, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=MeasureSet,
            temperature=0.2,
        ),
    )

    raw = json.loads(response.text)
    result = MeasureSet.model_validate(raw)
    return result.measures


def save_measures(measures: list[dict]) -> str:
    """Persist approved measures to output/measures.json."""
    _MEASURES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_MEASURES_FILE, "w", encoding="utf-8") as f:
        json.dump(measures, f, indent=2, ensure_ascii=False)
    return str(_MEASURES_FILE.resolve())


def load_measures() -> list[dict] | None:
    """Load previously saved measures."""
    if not _MEASURES_FILE.exists():
        return None
    with open(_MEASURES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
