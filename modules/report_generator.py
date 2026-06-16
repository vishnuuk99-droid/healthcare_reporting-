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
  - visual_type: One of card, bar_chart, stacked_bar, line_chart,
    donut_chart, treemap, table, matrix, kpi, gauge, slicer,
    scatter_chart, waterfall, funnel
  - dimensions: Columns from the star schema used as axis/legend/rows
  - measures: Measure names or inline DAX expressions
  - business_reason: Why this visual matters

**filters** – report-level slicers:
  - name, field (Table.Column), filter_type (slicer, dropdown,
    date_range, relative_date), default_value, scope (report or page)

**measures** – reusable DAX measures:
  - name, dax_expression, format_string, description, home_table

**drillthrough_pages** – detail pages users can right-click into:
  - page_name, purpose, drillthrough_field, visuals

Rules:
- Reference ONLY tables and columns present in the star schema model.
- Create DAX measures for every business metric in the analytics model.
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


def _load_analytics_model() -> dict | None:
    """Load the saved analytics model."""
    if not _ANALYTICS_MODEL_FILE.exists():
        return None
    with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_report_definition(
    requirements: dict,
    decisions: list[dict] | None = None,
) -> ReportDefinition:
    """
    Generate a Power BI report definition from the analytics model.

    Args:
        requirements: The extracted CMS requirements dict.
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
            response_schema=ReportDefinition,
            temperature=0.3,
        ),
    )

    raw = json.loads(response.text)
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
