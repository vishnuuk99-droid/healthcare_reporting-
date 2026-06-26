"""
DAX Generator – translates approved business measures, analytics model,
and data dictionary into valid Power BI DAX formulas.

Uses Gemini to generate DAX formulas with dependency injection, sorting
base measures first, and validating dependencies and syntax.
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import DAXEntry, DAXSet
from modules.file_manager import OUTPUT_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_MEASURES_FILE = OUTPUT_DIR / "measures.json"
_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_DATA_DICTIONARY_FILE = OUTPUT_DIR / "data_dictionary.json"
_DAX_OUTPUT_FILE = OUTPUT_DIR / "dax_artifacts.json"

ALLOWED_DAX_FUNCTIONS = {
    "COUNTROWS", "DISTINCTCOUNT", "SUM", "AVERAGE", "DIVIDE",
    "CALCULATE", "FILTER", "DATEDIFF", "ISBLANK", "NOT",
    "IF", "SWITCH", "ALL", "ALLEXCEPT", "VALUES",
    "SAMEPERIODLASTYEAR", "DATEADD", "PREVIOUSQUARTER",
    "TOTALYTD", "TOTALQTD", "KEEPFILTERS",
}

_SYSTEM_INSTRUCTION = """\
You are an expert Power BI DAX Architect. Your job is to translate business
measures into correct, production-grade Power BI DAX expressions.

You will receive:
1. The approved business measures (including name, type, classification,
   business definition, formula description, source tables, and source fields).
2. The star schema analytics model (with table schemas, columns, and relationships).
3. The data dictionary mapping report fields to database fields.

Your task: Generate a DAX measure for EACH approved business measure.

For EACH measure produce:
- measure_id: Exactly the same technical measure_id as the input business measure.
- display_name: Exactly the same canonical display_name as the input business measure.
- business_definition: Plain-language explanation of what the measure calculates.
- dax_expression: The DAX formula.
  - Base measures should query the star schema tables directly.
    Example: `COUNTROWS(FactOrganizationDetermination)` or `SUM(FactOrganizationDetermination[duration_days])` or `DISTINCTCOUNT(DimPatient[patient_key])`.
  - Derived measures and KPIs should reference other measures (using brackets syntax `[Display Name]`) to preserve dry principles and dependency chains. Power BI DAX requires the exact literal canonical display_name inside brackets.
    Example: `DIVIDE([Total Adverse Decisions], [Total Organization Determinations], 0)` or `CALCULATE([Total Decisions], FILTER(DimPatient, DimPatient[state] = "CA"))`.
- dependencies: The measure_ids of other DAX measures referenced in the `dax_expression`. If none, return an empty list `[]`.

Supported/Preferred DAX Functions:
- COUNTROWS
- DISTINCTCOUNT
- SUM
- AVERAGE
- DIVIDE
- CALCULATE
- FILTER

Order rules:
- Generate and sort the base measures first (which reference tables/columns directly).
- Follow with derived measures and KPIs (which build on top of base measures).
- Verify that every dependency is listed in the `dependencies` list.

If structured metric definitions are provided, use them to generate
CORRECT DAX:

- For Count metrics with exclusion rules:
  CALCULATE(COUNTROWS(FactTable),
    FactTable[column] <> "excluded_value",
    FactTable[status] <> "withdrawn")

- For Percentage/Ratio metrics with numerator and denominator:
  DIVIDE([Numerator Measure], [Denominator Measure], 0)

- For timeliness metrics (timeliness_days > 0):
  CALCULATE(COUNTROWS(FactTable),
    DATEDIFF(FactTable[request_date], FactTable[decision_date], DAY)
    <= timeliness_days)

- For reporting_period_type = "Quarterly" with period_anchor:
  Use TOTALQTD or DATEADD for period comparisons.

- For reporting_period_type = "Annual":
  Use TOTALYTD or SAMEPERIODLASTYEAR.

- For reporting_period_type = "PointInTime":
  Use LASTDATE or MAX for point-in-time snapshots.

- Set format_string: Count/Sum → "#,##0", Percentage/Ratio → "0.0%",
  Average → "#,##0.0"
- Set home_table to the primary source fact table.

CRITICAL RULES:
1. Do NOT generate placeholder DAX like KEEPFILTERS('literal text')
2. Do NOT repeat the measure name as the DAX expression
3. Every dax_expression MUST be valid, executable Power BI DAX
4. Every expression MUST reference actual table and column names
   from the analytics model
5. COUNTROWS(FactTable) without business filters is prohibited
   for CMS metrics that have inclusion or exclusion rules
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


def generate_dax_measures() -> list[DAXEntry]:
    """
    Generate DAX measures from approved business measures.

    Returns:
        A list of validated DAXEntry objects.
    """
    client = _get_client()

    measures = _load_json_file(_MEASURES_FILE)
    if not measures:
        raise ValueError(
            "No approved business measures found. Please generate and approve "
            "measures on the Measure Generator page first."
        )

    analytics_model = _load_json_file(_ANALYTICS_MODEL_FILE)
    if not analytics_model:
        raise ValueError(
            "No analytics model found. Please generate and approve "
            "the model on the Analytics Model page first."
        )

    data_dictionary = _load_json_file(_DATA_DICTIONARY_FILE)

    # Build context
    context_parts = []

    context_parts.append(
        f"=== APPROVED BUSINESS MEASURES ===\n"
        f"{json.dumps(measures, indent=2)}"
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

    requirements = _load_json_file(OUTPUT_DIR / "requirements.json")
    structured_metrics = requirements.get("structured_metrics", []) if requirements else []

    if structured_metrics:
        context_parts.append(
            f"=== STRUCTURED METRIC DEFINITIONS ===\n"
            f"Use these to generate CORRECT DAX expressions:\n"
            f"- numerator: what to count/sum in the numerator\n"
            f"- denominator: the denominator (for Ratio/Percentage types)\n"
            f"- exclusion_rules: records to EXCLUDE via FILTER or CALCULATE\n"
            f"- inclusion_rules: records to INCLUDE via FILTER or CALCULATE\n"
            f"- timeliness_days: threshold for DATEDIFF comparisons\n"
            f"- reporting_period_type + period_anchor: for date intelligence\n\n"
            f"{json.dumps(structured_metrics, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=DAXSet,
            temperature=0.2,
        ),
    )

    raw = json.loads(response.text)
    result = DAXSet.model_validate(raw)
    return result.dax_measures


def save_dax_artifacts(dax_list: list[dict]) -> str:
    """Persist approved DAX measures to output/dax_artifacts.json."""
    _DAX_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_DAX_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dax_list, f, indent=2, ensure_ascii=False)
    return str(_DAX_OUTPUT_FILE.resolve())


def load_dax_artifacts() -> list[dict] | None:
    """Load previously saved DAX measures."""
    if not _DAX_OUTPUT_FILE.exists():
        return None
    with open(_DAX_OUTPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def check_cycles(dax_measures: list[dict]) -> set[str]:
    """Detect nodes participating in circular dependencies using DFS."""
    adj = {}
    for m in dax_measures:
        name = m.get("measure_id", "")
        adj[name] = m.get("dependencies", [])

    visited = {}  # name -> 0=unvisited, 1=visiting, 2=visited
    cycle_nodes = set()

    def dfs(node):
        if node not in adj:
            return False  # Missing dependency is handled elsewhere
        visited[node] = 1  # visiting
        for neighbor in adj[node]:
            if visited.get(neighbor, 0) == 1:
                cycle_nodes.add(node)
                cycle_nodes.add(neighbor)
                return True
            elif visited.get(neighbor, 0) == 0:
                if dfs(neighbor):
                    cycle_nodes.add(node)
                    return True
        visited[node] = 2  # visited
        return False

    for node in adj:
        if visited.get(node, 0) == 0:
            dfs(node)

    return cycle_nodes


def validate_dax_measure(measure: dict, all_measure_names: set[str], cycle_nodes: set[str]) -> dict:
    """Validate a single DAX measure for cycles, missing dependencies, and supported functions."""
    errors = []
    warnings = []

    name = measure.get("measure_id", "")
    dax_expr = measure.get("dax_expression", "")
    deps = measure.get("dependencies", [])

    # 1. Cycle detection
    if name in cycle_nodes:
        errors.append("Circular dependency detected.")

    # 2. Missing dependency check
    for dep in deps:
        if dep not in all_measure_names:
            errors.append(f"Missing dependency: '{dep}' is not defined in the measures catalog.")

    # 3. Allowed functions check
    # Extract function names (uppercase words followed by open parenthesis)
    funcs_used = re.findall(r"\b([A-Z_]+)\s*\(", dax_expr)
    for fn in funcs_used:
        if fn not in ALLOWED_DAX_FUNCTIONS:
            warnings.append(f"Function '{fn}' is outside the officially supported list.")

    # Determine overall status
    if errors:
        status = "❌ Error"
    elif warnings:
        status = "⚠️ Warning"
    else:
        status = "✅ Valid"

    return {
        "status": status,
        "messages": errors + warnings
    }
