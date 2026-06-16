"""
File management utilities for storing and retrieving uploaded documents.

Supports both global (shared) and session-scoped (isolated) directories.
When a session is active, output and knowledge dirs are scoped to the
project workspace.  Shared resources (FHIR catalog, PDF uploads) remain
in the global knowledge directory.
"""

import os
from pathlib import Path
from typing import Optional

# Project root is one level up from the modules/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
OUTPUT_DIR = PROJECT_ROOT / "output"
SAMPLES_DIR = PROJECT_ROOT / "samples"
PROJECTS_DIR = PROJECT_ROOT / "projects"


def ensure_directories() -> None:
    """Create all required project directories if they don't exist."""
    for directory in [KNOWLEDGE_DIR, OUTPUT_DIR, SAMPLES_DIR, PROJECTS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def get_output_dir(session_output_dir: Optional[str] = None) -> Path:
    """
    Get the active output directory.

    Args:
        session_output_dir: If provided, returns this path as a Path object.
                            Otherwise falls back to the global OUTPUT_DIR.
    """
    if session_output_dir:
        p = Path(session_output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return OUTPUT_DIR


def get_knowledge_dir(session_knowledge_dir: Optional[str] = None) -> Path:
    """
    Get the active knowledge directory.

    Args:
        session_knowledge_dir: If provided, returns this path as a Path object.
                               Otherwise falls back to the global KNOWLEDGE_DIR.
    """
    if session_knowledge_dir:
        p = Path(session_knowledge_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    return KNOWLEDGE_DIR


def save_uploaded_file(uploaded_file, target_dir: Path | None = None) -> str:
    """
    Persist an uploaded file (from Streamlit's file_uploader) to disk.

    Args:
        uploaded_file: A Streamlit UploadedFile object.
        target_dir: Directory to save to. Defaults to KNOWLEDGE_DIR.

    Returns:
        The absolute path to the saved file.
    """
    if target_dir is None:
        target_dir = KNOWLEDGE_DIR

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / uploaded_file.name

    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return str(dest)


def list_stored_files(directory: Path | None = None) -> list[str]:
    """
    List all files in a given directory.

    Args:
        directory: Directory to scan. Defaults to KNOWLEDGE_DIR.

    Returns:
        Sorted list of filenames.
    """
    if directory is None:
        directory = KNOWLEDGE_DIR

    if not directory.exists():
        return []

    return sorted(
        f.name for f in directory.iterdir() if f.is_file()
    )
