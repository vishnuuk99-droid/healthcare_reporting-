"""
Report Definition Engine – generates Power BI report specs from the
analytics star schema model.

Uses Gemini to design an optimal Power BI report layout with pages,
visuals, DAX measures, filters, and drillthrough pages tailored to
CMS healthcare reporting requirements.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import ReportDefinition
from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_REPORT_DEFINITION_FILE = OUTPUT_DIR / "report_definition.json"

_SYSTEM_INSTRUCTION = """\
You are a Power BI report architect specialising in CMS healthcare
analytics.  You will receive a star schema analytics model, CMS
reporting requirements, and organizational decisions.

Design a complete Power BI report specification with the following
structure:

**report_name**: A clear, descriptive title for the report.

**pages** – each page has:
  - page_name: Tab label in Power BI
  - purpose: One-line description of what the page shows
  - visuals: List of visual objects

You MUST include these page categories (adapt titles to the data):
  1. **Executive Summary / KPI Dashboard** – high-level cards, gauges
     and trend sparklines for the most important KPIs.
  2. **Determinations Analysis** – breakdowns of organization
     determinations by disposition, decision rationale, processing
     priority, etc.
  3. **Appeals Analysis** – reconsideration volumes, overturn rates,
     physician review rates.
  4. **Provider Analysis** – provider NPI, contracted vs non-contracted,
     reviewer qualifications.
  5. **Trends & Timeliness** – time-series of request volumes, decision
     turnaround times, quarterly comparisons.
  Add additional pages if the requirements warrant them.

**visuals** – each visual has:
  - title: Displayed title
  - visual_type: The structural visual type chosen based on semantic rules:
    * card: Use for a single scalar metric with no trend or comparison dimension.
    * kpi: Use only when displaying a primary metric together with a meaningful time trend (Date, Month, Quarter, Year).
    * line_chart: Use for metrics analyzed over time.
    * bar_chart: Use for comparisons across categories.
    * donut_chart: Use for proportional distributions.
    * matrix: Use for grouped summaries with multiple dimensions.
    * table: Use for detailed records.
  - dimensions: Columns from the star schema used as axis/legend/rows
  - measures: List of objects containing measure_id and display_name. The display_name MUST be exactly preserved from the provided artifacts (including any parentheses).
  - business_reason: Why this visual matters

**filters** – report-level slicers:
  - name, field (Table.Column), filter_type (slicer, dropdown,
    date_range, relative_date), default_value, scope (report or page)

**measures** – reusable DAX measures:
  - measure_id, display_name, dax_expression, format_string, description, home_table

**drillthrough_pages** – detail pages users can right-click into:
  - page_name, purpose, drillthrough_field, visuals

Rules:
- Choose the simplest valid visual that satisfies the reporting requirement.
- If a metric does not include a valid trend dimension, NEVER select a KPI visual.
- Reference ONLY tables and columns present in the star schema model.
- You MUST only use measures that are explicitly defined in the provided artifacts (Analytics Model metrics or PRE-GENERATED DAX MEASURES). Do NOT invent new measures or hallucinate display names.
- Do NOT generate inline DAX expressions in the visuals. Only reference the pre-generated measures by their exact measure_id and display_name.
- Include at least one slicer/filter for each major dimension.
- Each page should have 4-8 visuals for a balanced layout.
- Use business-friendly titles, not technical column names.
- Apply organizational decisions — use mapped terms.
- Be thorough — cover all metrics and dimensions from the model.
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
    """Load a JSON file."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _load_analytics_model() -> dict | None:
    """Load the saved analytics model."""
    if not _ANALYTICS_MODEL_FILE.exists():
        return None
    with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_report_definition(
    requirements: dict,
    reporting_intent: list[dict] | None = None,
    decisions: list[dict] | None = None,
) -> ReportDefinition:
    """
    Generate a Power BI report definition from the analytics model.

    Args:
        requirements: The extracted CMS requirements dict.
        reporting_intent: The classified reporting intents list (optional).
        decisions: Organizational decisions list (optional).

    Returns:
        A validated ReportDefinition instance.
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
        f"=== STAR SCHEMA ANALYTICS MODEL ===\n"
        f"{json.dumps(analytics_model, indent=2)}"
    )

    context_parts.append(
        f"=== CMS REQUIREMENTS ===\n{json.dumps(requirements, indent=2)}"
    )

    if reporting_intent:
        context_parts.append(
            f"=== REPORTING INTENT ===\n{json.dumps(reporting_intent, indent=2)}"
        )
        
    dax_artifacts = _load_json_file(OUTPUT_DIR / "dax_artifacts.json")
    if dax_artifacts:
        context_parts.append(
            f"=== PRE-GENERATED DAX MEASURES ===\n"
            f"You must select exact measure names from this list for your visuals:\n"
            f"{json.dumps(dax_artifacts, indent=2)}"
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
            response_schema=ReportDefinition,
            temperature=0.3,
        ),
    )

    raw = json.loads(response.text)
    
    from modules.report_definition_validator import validate_report_definition
    validation_errors = validate_report_definition(raw)
    if validation_errors:
        error_msg = "\n".join(validation_errors)
        raise ValueError(f"Report Definition Validation failed. The following visual specifications are structurally invalid:\n{error_msg}")

    return ReportDefinition.model_validate(raw)


def save_report_definition(report: ReportDefinition) -> str:
    """Persist the report definition to output/report_definition.json."""
    _REPORT_DEFINITION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_DEFINITION_FILE, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))
    return str(_REPORT_DEFINITION_FILE.resolve())


def load_report_definition() -> dict | None:
    """Load a previously saved report definition."""
    if not _REPORT_DEFINITION_FILE.exists():
        return None
    with open(_REPORT_DEFINITION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
