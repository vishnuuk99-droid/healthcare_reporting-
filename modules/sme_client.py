"""
SME Collaboration client – Gemini-powered chat for requirement clarification.

The AI has full context of the extracted CMS text, the structured
requirements, and all prior organizational decisions.  It classifies
each user statement and returns a structured response.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from modules.schemas import SMEChatResponse

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_SYSTEM_INSTRUCTION = """\
You are an SME (Subject Matter Expert) collaboration assistant for a
healthcare reporting team.  You help analysts refine CMS reporting
requirements by interpreting their clarifications and decisions.

You have access to:
1. The extracted CMS document text.
2. The structured requirements JSON already produced.
3. All prior organizational decisions.

When the user makes a statement, you MUST classify it as one of:
- "terminology_clarification" – mapping one term to another
  (e.g., "Disposition means Decision Outcome")
- "business_rule" – a rule that governs how data should be handled
  (e.g., "Telehealth visits should count as encounters")
- "reporting_preference" – a preference on how results are displayed
  or reported (e.g., "Show percentages instead of raw counts")

For every classified statement, extract:
- source_term: the original term or concept from the CMS document
- mapped_term: the organization's preferred term or interpretation
- description: a clear explanation of the decision and its impact

If the user asks a general question that is NOT a decision, respond
helpfully but set is_decision to false.

Always be concise, precise, and professional.
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


def build_context(
    cms_text: str | None,
    requirements_json: dict | None,
    prior_decisions: list[dict] | None,
) -> str:
    """Assemble the full context block that gets prepended to each chat turn."""
    parts: list[str] = []

    if cms_text:
        # Truncate very long documents to keep within context limits
        truncated = cms_text[:30_000] if len(cms_text) > 30_000 else cms_text
        parts.append(f"=== CMS DOCUMENT TEXT ===\n{truncated}")

    if requirements_json:
        parts.append(
            f"=== EXTRACTED REQUIREMENTS ===\n"
            f"{json.dumps(requirements_json, indent=2)}"
        )

    if prior_decisions:
        parts.append(
            f"=== PRIOR ORGANIZATIONAL DECISIONS ===\n"
            f"{json.dumps(prior_decisions, indent=2)}"
        )

    return "\n\n".join(parts)


def chat_with_sme(
    user_message: str,
    context: str,
    chat_history: list[dict] | None = None,
) -> SMEChatResponse:
    """
    Send the user's message (with full context) to Gemini and return
    a structured SMEChatResponse.

    Args:
        user_message:  The SME's latest input.
        context:       Pre-built context string from build_context().
        chat_history:  Prior turns as [{"role": "user"|"model", "text": ...}].

    Returns:
        A validated SMEChatResponse.
    """
    client = _get_client()

    # Build message contents: context + history + new message
    contents: list[types.Content] = []

    # Inject context as the first user turn
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=f"[CONTEXT]\n{context}")]
        )
    )
    contents.append(
        types.Content(
            role="model",
            parts=[types.Part(
                text="Understood. I have the CMS document, extracted "
                     "requirements, and prior decisions loaded. "
                     "How can I help you refine the requirements?"
            )]
        )
    )

    # Append chat history
    if chat_history:
        for turn in chat_history:
            contents.append(
                types.Content(
                    role=turn["role"],
                    parts=[types.Part(text=turn["text"])],
                )
            )

    # Append new user message
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=SMEChatResponse,
            temperature=0.3,
        ),
    )

    raw = json.loads(response.text)
    return SMEChatResponse.model_validate(raw)
