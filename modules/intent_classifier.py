"""
Reporting Intent Engine – classifies CMS requirements into reporting
intent categories and recommends Power BI visual types.

Uses Gemini to analyze each requirement and determine whether it
calls for a Detail Listing, KPI, Trend Analysis, Comparison Analysis,
Cross Tabulation, Data Submission, Data Quality check, or Compliance
Monitoring visual.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import ReportingIntent, ReportingIntentSet
from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_INTENT_OUTPUT_FILE = OUTPUT_DIR / "reporting_intent.json"

# Intent → recommended visual mapping
INTENT_VISUAL_MAP = {
    "detail_listing": "Table",
    "kpi": "Card",
    "trend_analysis": "Line Chart",
    "comparison_analysis": "Bar Chart",
    "cross_tabulation": "Matrix",
    "data_submission": "Table + Export",
    "data_quality": "Table + KPI",
    "compliance_monitoring": "KPI + Trend",
}

VALID_INTENTS = list(INTENT_VISUAL_MAP.keys())

_SYSTEM_INSTRUCTION = """\
You are a healthcare reporting analyst specialising in CMS data
reporting and Power BI design.  You will receive:

1. CMS reporting requirements (metrics, dimensions, filters, business
   rules, exclusions).
2. A star schema analytics model with fact/dimension tables and columns.
3. Organizational decisions from SME reviews.

For EACH distinct requirement (metrics, dimensions, business rules,
filters, exclusions — each individual item), classify its **reporting
intent** into exactly one of these categories:

- **detail_listing**: The requirement asks to list, enumerate, or
  display individual records (e.g., "report all OD numbers").
- **kpi**: The requirement asks for a single summary number or
  indicator (e.g., "total determinations count").
- **trend_analysis**: The requirement asks for change over time
  (e.g., "quarterly volume trends").
- **comparison_analysis**: The requirement asks to compare groups
  (e.g., "adverse vs. favorable by contract").
- **cross_tabulation**: The requirement asks for a pivot/matrix view
  (e.g., "disposition by requesting party and contract").
- **data_submission**: The requirement describes a data element
  that must be submitted (file/upload) to CMS.
- **data_quality**: The requirement defines a validation check or
  data quality rule.
- **compliance_monitoring**: The requirement defines an ongoing
  compliance obligation or monitoring threshold.

For each classified requirement produce:
- requirement: The exact requirement text.
- intent: One of the categories above (lowercase with underscores).
- recommended_visual: The recommended Power BI visual type based on:
    detail_listing → Table
    kpi → Card
    trend_analysis → Line Chart
    comparison_analysis → Bar Chart
    cross_tabulation → Matrix
    data_submission → Table + Export
    data_quality → Table + KPI
    compliance_monitoring → KPI + Trend
- required_columns: Which star schema columns are needed.
- reasoning: Brief explanation of why this intent was chosen.

Rules:
- Classify EVERY requirement item (each metric, dimension, filter,
  business rule, and exclusion as a separate entry).
- Use only the intent categories listed above.
- Reference only columns present in the star schema model.
- Apply organizational decisions when they affect terminology.
- Be precise — if a rule is about data accuracy, classify as
  data_quality, not compliance_monitoring.
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


def _load_analytics_model() -> dict | None:
    """Load the saved analytics model."""
    if not _ANALYTICS_MODEL_FILE.exists():
        return None
    with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_reporting_intents(
    requirements: dict,
    decisions: list[dict] | None = None,
) -> list[ReportingIntent]:
    """
    Classify CMS requirements into reporting intent categories.

    Args:
        requirements: The extracted CMS requirements dict.
        decisions: Organizational decisions list (optional).

    Returns:
        A list of validated ReportingIntent objects.
    """
    client = _get_client()
    analytics_model = _load_analytics_model()

    if not analytics_model:
        raise ValueError(
            "No analytics model found. Please generate and approve "
            "the analytics model on the Analytics Model page first."
        )

    # Build context
    context_parts = []

    context_parts.append(
        f"=== CMS REQUIREMENTS ===\n{json.dumps(requirements, indent=2)}"
    )

    context_parts.append(
        f"=== STAR SCHEMA ANALYTICS MODEL ===\n"
        f"{json.dumps(analytics_model, indent=2)}"
    )

    if decisions:
        context_parts.append(
            f"=== ORGANIZATIONAL DECISIONS ===\n{json.dumps(decisions, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ReportingIntentSet,
            temperature=0.2,
        ),
    )

    raw = json.loads(response.text)
    result = ReportingIntentSet.model_validate(raw)
    return result.intents


def save_reporting_intents(intents: list[dict]) -> str:
    """Persist approved reporting intents to output/reporting_intent.json."""
    _INTENT_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_INTENT_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(intents, f, indent=2, ensure_ascii=False)
    return str(_INTENT_OUTPUT_FILE.resolve())


def load_reporting_intents() -> list[dict] | None:
    """Load previously saved reporting intents."""
    if not _INTENT_OUTPUT_FILE.exists():
        return None
    with open(_INTENT_OUTPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
