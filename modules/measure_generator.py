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
- measure_id: Stable technical identifier (e.g., "total_organization_determinations").
- display_name: Exact canonical business label (e.g., "Total Organization Determinations", "Adverse Decision Rate (Standard)"). You MUST preserve the exact characters from the report definition or provided artifacts.
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
  "COUNTROWS(FILTER(FactOrganizationDetermination, disposition = 'Adverse'))"
- source_fields: List of star schema column names consumed by this
  measure (e.g., ["od_number", "disposition", "date_of_decision_key"]).
- source_tables: List of star schema tables this measure draws from
  (e.g., ["FactOrganizationDetermination", "DimDate"]).
- classification: Exactly one of:
    - **Base Measure**: A foundational measure that does not depend on
      other measures (e.g., total count, sum).
    - **Derived Measure**: A measure computed from one or more base
      measures (e.g., rate = adverse / total).
    - **KPI**: A key performance indicator with a target or threshold
      (e.g., timeliness rate, compliance percentage).
- dependencies: List of measure_ids of other measures that this measure depends on.
  For Base Measures, this must be an empty list []. For Derived Measures
  or KPIs, list the exact measure_ids that are used in its calculation
  (e.g. if Adverse Rate = Adverse Decisions / Total Decisions, it depends on
  ["total_adverse_decisions", "total_decisions"]).
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

Additionally, if structured metric definitions are provided:
- Set numerator_definition to the numerator from the structured metric.
- Set denominator_definition to the denominator from the structured metric.
- Set exclusion_filters to the exclusion_rules from the structured metric.
- Set timeliness_threshold to the timeliness_days value.
- Use inclusion_rules and exclusion_rules to generate accurate
  formula_description values that reflect actual business logic.
- Do NOT generate placeholder measures. Every measure must be traceable
  to a specific CMS metric definition.
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


def validate_structured_metrics(structured_metrics: list[dict]) -> dict:
    """
    Semantic validation checkpoint (Enhancement 4).
    Validates structured metric definitions before measure generation.

    Returns:
        dict with pass/fail status, issues list, and metrics breakdown.
    """
    issues = []
    valid_count = 0
    low_confidence = []

    required_fields = ["metric_name", "metric_type", "numerator"]

    for sm in structured_metrics:
        metric_name = sm.get("metric_name", "(unnamed)")
        missing = [f for f in required_fields if not sm.get(f)]

        if missing:
            issues.append({
                "metric": metric_name,
                "severity": "Error",
                "issue": f"Missing critical fields: {', '.join(missing)}",
            })
        else:
            valid_count += 1

        # Enhancement 1: Flag low-confidence interpretations
        confidence = sm.get("confidence_score", 0.0)
        if confidence < 0.80:
            low_confidence.append({
                "metric": metric_name,
                "confidence": confidence,
                "notes": sm.get("extraction_notes", ""),
            })

        # Enhancement 2: Validate reporting period structure
        rp_type = sm.get("reporting_period_type", "")
        if rp_type and rp_type not in ("Quarterly", "Annual", "Monthly", "PointInTime"):
            issues.append({
                "metric": metric_name,
                "severity": "Warning",
                "issue": f"Invalid reporting_period_type: '{rp_type}'",
            })

        # Validate metric_type
        valid_types = {"Count", "Sum", "Average", "Percentage", "Ratio", "Distinct Count"}
        mt = sm.get("metric_type", "")
        if mt and mt not in valid_types:
            issues.append({
                "metric": metric_name,
                "severity": "Warning",
                "issue": f"Invalid metric_type: '{mt}'",
            })

    total = len(structured_metrics)
    pass_rate = (valid_count / total * 100) if total > 0 else 0.0

    return {
        "status": "PASS" if pass_rate >= 50.0 else "FAIL",
        "total_metrics": total,
        "valid_metrics": valid_count,
        "pass_rate": round(pass_rate, 1),
        "issues": issues,
        "low_confidence_metrics": low_confidence,
    }


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

    # Semantic validation checkpoint (Enhancement 4)
    structured_metrics = requirements.get("structured_metrics", []) if requirements else []
    if structured_metrics:
        validation = validate_structured_metrics(structured_metrics)
        if validation["status"] == "FAIL":
            raise ValueError(
                f"Semantic validation failed. Pass rate: {validation['pass_rate']}%. "
                f"Issues: {json.dumps(validation['issues'], indent=2)}\n"
                f"Fix structured metric definitions before generating measures."
            )

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

    if structured_metrics:
        context_parts.append(
            f"=== STRUCTURED METRIC DEFINITIONS ===\n"
            f"These contain the authoritative numerator, denominator, "
            f"inclusion/exclusion rules, and timeliness thresholds.\n"
            f"Use these to populate numerator_definition, denominator_definition, "
            f"exclusion_filters, and timeliness_threshold on each measure.\n"
            f"Every measure MUST trace back to:\n"
            f"  Metric Definition → Numerator → Denominator → Aggregation Logic\n"
            f"{json.dumps(structured_metrics, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-2.0-flash",
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
