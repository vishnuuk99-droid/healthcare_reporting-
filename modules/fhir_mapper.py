"""
FHIR Mapping Engine – maps CMS concepts to FHIR US Core R4 resources.

Uses Gemini with structured output to produce high-quality mappings,
taking into account the FHIR catalog, extracted requirements,
organizational decisions, and any previously approved mappings.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import FHIRCatalogEntry, FHIRMapping, FHIRMappingSet
from modules.file_manager import KNOWLEDGE_DIR

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_CATALOG_FILE = KNOWLEDGE_DIR / "fhir_catalog.json"
_MAPPING_CACHE_FILE = KNOWLEDGE_DIR / "mapping_cache.json"

_SYSTEM_INSTRUCTION = """\
You are a FHIR interoperability expert specializing in US Core R4 and
CMS healthcare data. Your job is to map CMS reporting concepts to the
most appropriate FHIR resources and fields.

You will receive:
1. A FHIR resource catalog with supported resources, profiles, and fields.
2. Extracted CMS reporting requirements (metrics, dimensions, filters, etc.).
3. Organizational decisions that may redefine terminology or add rules.
4. Any previously approved mappings that should be respected.

For EACH distinct CMS concept found in the requirements, produce a mapping:
- concept: The CMS concept being mapped (use the exact term from requirements).
- fhir_resource: The best matching FHIR resource type.
- fhir_field: The specific field within that resource.
- confidence: "high", "medium", or "low" based on how certain the mapping is.
- reasoning: A brief explanation of why this mapping was chosen.

Rules:
- Only map to resources listed in the catalog.
- Prefer US Core profiles.
- Consider organizational decisions — if an SME redefined a term, use
  their definition when choosing the mapping.
- If a concept could map to multiple resources, pick the most specific one
  and note alternatives in reasoning.
- Set confidence to "low" for ambiguous mappings that need SME review.
- Extract concepts from ALL requirement fields: metrics, dimensions,
  filters, business_rules, exclusions, reporting_entities.
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


def load_fhir_catalog() -> list[FHIRCatalogEntry]:
    """Load the FHIR semantic catalog from disk."""
    if not _CATALOG_FILE.exists():
        return []
    with open(_CATALOG_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [FHIRCatalogEntry.model_validate(entry) for entry in raw]


def load_mapping_cache() -> list[dict]:
    """Load previously approved/overridden mappings."""
    if not _MAPPING_CACHE_FILE.exists():
        return []
    with open(_MAPPING_CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_mapping_cache(mappings: list[dict]) -> str:
    """Persist the approved mapping cache to disk."""
    _MAPPING_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_MAPPING_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)
    return str(_MAPPING_CACHE_FILE.resolve())


def generate_mappings(
    requirements: dict,
    decisions: list[dict] | None = None,
) -> list[FHIRMapping]:
    """
    Use Gemini to map CMS concepts from requirements to FHIR resources.

    Args:
        requirements: The extracted requirements JSON dict.
        decisions: Organizational decisions (optional).

    Returns:
        A list of validated FHIRMapping objects.
    """
    client = _get_client()
    catalog = load_fhir_catalog()
    cached = load_mapping_cache()

    # Build context for Gemini
    context_parts = []

    # 1. FHIR Catalog
    catalog_data = [c.model_dump() for c in catalog]
    context_parts.append(
        f"=== FHIR US CORE R4 CATALOG ===\n{json.dumps(catalog_data, indent=2)}"
    )

    # 2. Requirements
    context_parts.append(
        f"=== CMS REQUIREMENTS ===\n{json.dumps(requirements, indent=2)}"
    )

    # 3. Organizational decisions
    if decisions:
        context_parts.append(
            f"=== ORGANIZATIONAL DECISIONS ===\n{json.dumps(decisions, indent=2)}"
        )

    # 4. Previously approved mappings
    if cached:
        context_parts.append(
            f"=== PREVIOUSLY APPROVED MAPPINGS (respect these) ===\n"
            f"{json.dumps(cached, indent=2)}"
        )

    content = "\n\n".join(context_parts)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=FHIRMappingSet,
            temperature=0.2,
        ),
    )

    raw = json.loads(response.text)
    result = FHIRMappingSet.model_validate(raw)
    return result.mappings


def approve_mapping(mapping: dict) -> None:
    """Add or update an approved mapping in the cache."""
    cached = load_mapping_cache()

    # Replace if same concept exists
    cached = [m for m in cached if m.get("concept") != mapping.get("concept")]
    mapping["status"] = "approved"
    cached.append(mapping)

    save_mapping_cache(cached)


def override_mapping(concept: str, new_resource: str, new_field: str, reasoning: str) -> dict:
    """Override a mapping with user-specified values."""
    cached = load_mapping_cache()
    cached = [m for m in cached if m.get("concept") != concept]

    overridden = {
        "concept": concept,
        "fhir_resource": new_resource,
        "fhir_field": new_field,
        "confidence": "high",
        "reasoning": f"[SME Override] {reasoning}",
        "status": "overridden",
    }
    cached.append(overridden)
    save_mapping_cache(cached)
    return overridden


def remove_from_cache(concept: str) -> bool:
    """Remove a mapping from the cache by concept name."""
    cached = load_mapping_cache()
    filtered = [m for m in cached if m.get("concept") != concept]
    if len(filtered) == len(cached):
        return False
    save_mapping_cache(filtered)
    return True
