"""
FRS Processor – Extracts structured requirements from a Functional
Requirements Specification (FRS) document using Gemini.

The FRS is optional.  When provided it enriches the AI's understanding
of KPIs, page expectations, and visualisation preferences.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import FRSRequirements

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ── System prompt ────────────────────────────────────────────────────
_FRS_SYSTEM_INSTRUCTION = """\
You are a healthcare business analyst AI.  Your job is to read a
Functional Requirements Specification (FRS) document and extract
structured requirements that will be used to build a Power BI report.

Analyze the document carefully and extract:

- business_definitions: List of {"term": "...", "definition": "..."} dicts.
  These are business-specific terms and their definitions.

- kpi_definitions: List of KPI objects with fields:
    name, definition, formula, target, visual_type

- page_expectations: List of expected report pages with fields:
    page_name, purpose, expected_visuals (list), expected_kpis (list)

- visualization_expectations: List of {"visual_type": "...", "context": "...", "fields": [...]}
  describing expected visualisation types and their data bindings.

- filters: List of expected report-level filters (strings).

- dimensions: List of expected slicing/grouping axes (strings).

- drillthrough_requirements: List of drillthrough scenarios (strings).

- user_expectations: List of user-facing interaction expectations (strings).

Be thorough.  If a field has no relevant information, leave it as an
empty list.
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


def extract_frs_requirements(frs_text: str) -> FRSRequirements:
    """
    Send FRS document text to Gemini and return structured requirements.

    Args:
        frs_text: The full extracted text from an FRS document.

    Returns:
        A validated FRSRequirements Pydantic model instance.

    Raises:
        EnvironmentError: If GEMINI_API_KEY is not set.
        Exception: If Gemini returns an unparsable response.
    """
    client = _get_client()

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=frs_text,
        config=types.GenerateContentConfig(
            system_instruction=_FRS_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=FRSRequirements,
            temperature=0.2,
        ),
    )

    raw_json = json.loads(response.text)
    return FRSRequirements.model_validate(raw_json)


def save_frs_requirements(
    frs_req: FRSRequirements,
    output_path: str | Path,
) -> str:
    """
    Persist extracted FRS requirements to a JSON file.

    Args:
        frs_req: Validated FRSRequirements instance.
        output_path: File path to write the JSON to.

    Returns:
        The absolute path of the saved file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(frs_req.model_dump_json(indent=2))

    return str(output_path.resolve())


def load_frs_requirements(output_dir: str | Path) -> FRSRequirements | None:
    """Load previously saved FRS requirements from disk."""
    path = Path(output_dir) / "frs_requirements.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return FRSRequirements.model_validate(data)
    except Exception:
        return None
