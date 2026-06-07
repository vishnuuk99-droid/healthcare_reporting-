"""
PBIP Generator – compiles approved analytics models, report definitions,
and DAX measures into a standard Power BI Project (PBIP) folder structure
and bundles it as a downloadable ZIP package.

Folder structure follows the official Power BI Desktop PBIP specification
with PBIR (Power BI Enhanced Report) format:

    report.pbip
    metadata.json
    report.Report/
        definition.pbir
        definition/
            report.json
            pages/
                <PageName>/
                    page.json
                    visuals/
                        <visual_id>.json
        .pbi/
            localSettings.json
    report.SemanticModel/
        definition.pbism
        definition/
            model.tmdl
            tables/
                _Measures.tmdl
        .pbi/
            localSettings.json
"""

import json
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR

_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_REPORT_DEFINITION_FILE = OUTPUT_DIR / "report_definition.json"
_INTENT_FILE = OUTPUT_DIR / "reporting_intent.json"
_DATA_DICTIONARY_FILE = OUTPUT_DIR / "data_dictionary.json"
_MEASURES_FILE = OUTPUT_DIR / "measures.json"
_DAX_ARTIFACTS_FILE = OUTPUT_DIR / "dax_artifacts.json"

_PBIP_DIR = OUTPUT_DIR / "pbip"
_ZIP_FILE = OUTPUT_DIR / "pbip_project.zip"

# ── Official PBIP required file manifest ─────────────────────────────
# Dynamically defined based on current report definition.
project_slug_temp = "Healthcare_Reporting_AI"
if _REPORT_DEFINITION_FILE.exists():
    try:
        with open(_REPORT_DEFINITION_FILE, "r", encoding="utf-8") as f:
            report_def_temp = json.load(f)
            project_slug_temp = _slugify(report_def_temp.get("report_name", "Healthcare_Reporting_AI"))
    except Exception:
        pass

PBIP_REQUIRED_FILES = [
    (f"{project_slug_temp}.pbip", "Project entry point"),
    ("metadata.json", "Generation metadata"),
    (f"{project_slug_temp}.Report/definition.pbir", "Report config – links to semantic model"),
    (f"{project_slug_temp}.Report/report.json", "Report layout metadata (legacy format)"),
    (f"{project_slug_temp}.SemanticModel/definition.pbism", "Semantic model configuration"),
    (f"{project_slug_temp}.SemanticModel/model.bim", "Semantic model (TMSL/TOM format)"),
    (f"{project_slug_temp}.SemanticModel/definition/model.tmdl", "Model definition (TMDL format)"),
    (f"{project_slug_temp}.SemanticModel/definition/tables/_Measures.tmdl", "DAX measures table (TMDL)"),
    (f"{project_slug_temp}.SemanticModel/.pbi/localSettings.json", "Semantic model local settings"),
    (f"{project_slug_temp}.SemanticModel/.pbi/version.json", "Semantic model version metadata"),
]


def _slugify(name: str) -> str:
    """Convert a page/visual name to a safe folder name."""
    slug = re.sub(r"[^\w\s-]", "", name).strip()
    slug = re.sub(r"[\s]+", "_", slug)
    return slug or "unnamed"


def get_project_slug() -> str:
    """Helper to get the current project slug from metadata or report definition."""
    metadata_path = _PBIP_DIR / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                if "project_slug" in meta:
                    return meta["project_slug"]
        except Exception:
            pass

    if _REPORT_DEFINITION_FILE.exists():
        try:
            with open(_REPORT_DEFINITION_FILE, "r", encoding="utf-8") as f:
                report_def = json.load(f)
                name = report_def.get("report_name", "Healthcare_Reporting_AI")
                return _slugify(name)
        except Exception:
            pass

    return "Healthcare_Reporting_AI"


def get_required_files(project_slug: str) -> list[tuple[str, str]]:
    return [
        (f"{project_slug}.pbip", "Project entry point"),
        ("metadata.json", "Generation metadata"),
        (f"{project_slug}.Report/definition.pbir", "Report config – links to semantic model"),
        (f"{project_slug}.Report/report.json", "Report layout metadata (legacy format)"),
        (f"{project_slug}.SemanticModel/definition.pbism", "Semantic model configuration"),
        (f"{project_slug}.SemanticModel/model.bim", "Semantic model (TMSL/TOM format)"),
        (f"{project_slug}.SemanticModel/definition/model.tmdl", "Model definition (TMDL format)"),
        (f"{project_slug}.SemanticModel/definition/tables/_Measures.tmdl", "DAX measures table (TMDL)"),
        (f"{project_slug}.SemanticModel/.pbi/localSettings.json", "Semantic model local settings"),
        (f"{project_slug}.SemanticModel/.pbi/version.json", "Semantic model version metadata"),
    ]


def map_visual_type(raw_type: str, intent: str = "") -> str:
    """
    Maps Power BI visual types and reporting intents to the supported set:
    Card, Table, Matrix, Line Chart, Bar Chart.
    """
    raw_lower = raw_type.lower()
    intent_lower = intent.lower() if intent else ""

    # Check intent-driven visual overrides first
    if intent_lower == "kpi":
        return "Card"
    elif intent_lower == "trend_analysis":
        return "Line Chart"
    elif intent_lower in ("detail_listing", "data_submission"):
        return "Table"
    elif intent_lower == "cross_tabulation":
        return "Matrix"
    elif intent_lower == "comparison_analysis":
        return "Bar Chart"

    # Fallback to standard mappings
    if "card" in raw_lower or "gauge" in raw_lower or "kpi" in raw_lower:
        return "Card"
    elif "line" in raw_lower or "trend" in raw_lower:
        return "Line Chart"
    elif "bar" in raw_lower or "column" in raw_lower or "donut" in raw_lower or "pie" in raw_lower or "treemap" in raw_lower:
        return "Bar Chart"
    elif "matrix" in raw_lower:
        return "Matrix"
    else:
        return "Table"


# Visual type to Power BI internal visual type ID mapping
_VISUAL_TYPE_MAP = {
    "Card": "card",
    "Table": "tableEx",
    "Matrix": "pivotTable",
    "Line Chart": "lineChart",
    "Bar Chart": "clusteredBarChart",
}


def compile_pbip_project() -> dict:
    """
    Compile the PBIP project and write files into the official folder structure
    under output/pbip/.  Also creates the compiled ZIP package.

    Returns:
        A dict containing status, file details, and validation logs.
    """
    # ── Load Inputs ──────────────────────────────────────────────────
    if not _ANALYTICS_MODEL_FILE.exists():
        raise ValueError("Analytics Model missing. Please generate it first.")
    if not _REPORT_DEFINITION_FILE.exists():
        raise ValueError("Report Definition missing. Please generate it first.")
    if not _DAX_ARTIFACTS_FILE.exists():
        raise ValueError("DAX Artifacts missing. Please generate it first.")

    with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
        analytics = json.load(f)
    with open(_REPORT_DEFINITION_FILE, "r", encoding="utf-8") as f:
        report_def = json.load(f)
    with open(_DAX_ARTIFACTS_FILE, "r", encoding="utf-8") as f:
        dax_list = json.load(f)

    intents = []
    if _INTENT_FILE.exists():
        with open(_INTENT_FILE, "r", encoding="utf-8") as f:
            intents_data = json.load(f)
            intents = intents_data.get("intents", []) if isinstance(intents_data, dict) else intents_data

    # ── Prepare Output Directories ───────────────────────────────────
    if _PBIP_DIR.exists():
        shutil.rmtree(_PBIP_DIR)

    project_name_raw = report_def.get("report_name", "Healthcare_Reporting_AI")
    project_slug = _slugify(project_name_raw)

    # Create all required sub-directories
    report_dir = _PBIP_DIR / f"{project_slug}.Report"
    report_pbi_dir = report_dir / ".pbi"
    sm_dir = _PBIP_DIR / f"{project_slug}.SemanticModel"
    sm_def_dir = sm_dir / "definition"
    sm_tables_dir = sm_def_dir / "tables"
    sm_pbi_dir = sm_dir / ".pbi"

    for d in [_PBIP_DIR, report_dir, report_pbi_dir, sm_dir, sm_def_dir, sm_tables_dir, sm_pbi_dir]:
        d.mkdir(parents=True, exist_ok=True)

    file_paths = {}  # logical name -> absolute Path

    # ── 1. <ProjectName>.pbip (project root) ─────────────────────────
    pbip_data = {
        "version": "1.0",
        "artifacts": [
            {
                "report": {
                    "path": f"{project_slug}.Report"
                }
            }
        ]
    }
    pbip_path = _PBIP_DIR / f"{project_slug}.pbip"
    _write_json(pbip_path, pbip_data)
    file_paths[f"{project_slug}.pbip"] = pbip_path

    # ── 2. <ProjectName>.Report/definition.pbir ──────────────────────
    pbir_data = {
        "version": "1.0",
        "datasetReference": {
            "byPath": {
                "path": f"../{project_slug}.SemanticModel"
            },
            "byConnection": None
        }
    }
    pbir_path = report_dir / "definition.pbir"
    _write_json(pbir_path, pbir_data)
    file_paths[f"{project_slug}.Report/definition.pbir"] = pbir_path

    # ── 2b. <ProjectName>.Report/.pbi/localSettings.json & version.json ─
    report_local_settings = {
        "version": "1.0"
    }
    report_ls_path = report_pbi_dir / "localSettings.json"
    _write_json(report_ls_path, report_local_settings)
    file_paths[f"{project_slug}.Report/.pbi/localSettings.json"] = report_ls_path

    report_version = {"version": "1.0"}
    report_ver_path = report_pbi_dir / "version.json"
    _write_json(report_ver_path, report_version)
    file_paths[f"{project_slug}.Report/.pbi/version.json"] = report_ver_path

    # ── 4. <ProjectName>.SemanticModel/definition.pbism ──────────────
    pbism_data = {
        "version": "1.0",
        "settings": {}
    }
    pbism_path = sm_dir / "definition.pbism"
    _write_json(pbism_path, pbism_data)
    file_paths[f"{project_slug}.SemanticModel/definition.pbism"] = pbism_path

    # ── 5. <ProjectName>.SemanticModel/.pbi/localSettings.json ───────
    sm_local_settings = {
        "version": "1.0"
    }
    sm_ls_path = sm_pbi_dir / "localSettings.json"
    _write_json(sm_ls_path, sm_local_settings)
    file_paths[f"{project_slug}.SemanticModel/.pbi/localSettings.json"] = sm_ls_path

    # version.json for SemanticModel .pbi folder
    sm_version = {"version": "1.0"}
    sm_ver_path = sm_pbi_dir / "version.json"
    _write_json(sm_ver_path, sm_version)
    file_paths[f"{project_slug}.SemanticModel/.pbi/version.json"] = sm_ver_path

    # ── Build Data Structures ────────────────────────────────────────
    tables_list = []

    # Fact tables
    for fact in analytics.get("fact_tables", []):
        cols = [{"name": c["name"], "dataType": c["data_type"], "sourceColumn": c["name"]} for c in fact.get("columns", [])]
        tables_list.append({
            "name": fact["name"],
            "description": fact.get("description", ""),
            "columns": cols,
            "measures": []
        })

    # Dimension tables
    for dim in analytics.get("dimension_tables", []):
        cols = [{"name": c["name"], "dataType": c["data_type"], "sourceColumn": c["name"]} for c in dim.get("columns", [])]
        tables_list.append({
            "name": dim["name"],
            "description": dim.get("description", ""),
            "columns": cols,
            "measures": []
        })

    # Measures Table (holding the DAX measures)
    measures_converted = []
    for dax in dax_list:
        measures_converted.append({
            "name": dax["measure_name"],
            "expression": dax["dax_expression"],
            "description": dax.get("business_definition", "")
        })
    tables_list.append({
        "name": "_Measures",
        "description": "Consolidated business and compliance measures.",
        "columns": [{"name": "_placeholder", "dataType": "string", "sourceColumn": None}],
        "measures": measures_converted
    })

    # Build lookup: dimension table name -> primary key column name
    dim_pk_lookup = {}
    for dim in analytics.get("dimension_tables", []):
        cols = dim.get("columns", [])
        if cols:
            dim_pk_lookup[dim["name"]] = cols[0]["name"]
    for fact in analytics.get("fact_tables", []):
        cols = fact.get("columns", [])
        if cols:
            dim_pk_lookup[fact["name"]] = cols[0]["name"]

    # Relationships – only one active relationship allowed per table pair in PBI
    relationships_list = []
    seen_table_pairs = set()
    for rel in analytics.get("relationships", []):
        to_table = rel["dimension_table"]
        to_column = dim_pk_lookup.get(to_table, rel["join_key"])
        pair_key = (rel["fact_table"], to_table)
        is_active = rel.get("is_active", True) and pair_key not in seen_table_pairs
        seen_table_pairs.add(pair_key)
        relationships_list.append({
            "name": f"{rel['fact_table']}_{to_table}_{rel['join_key']}",
            "fromTable": rel["fact_table"],
            "fromColumn": rel["join_key"],
            "toTable": to_table,
            "toColumn": to_column,
            "cardinality": "manyToOne" if rel.get("relationship_type") == "many-to-one" else "manyToMany",
            "isActive": is_active
        })

    # ── 6. <ProjectName>.SemanticModel/definition/model.tmdl ─────────
    tmdl_lines = [
        "model Model",
        "\tcompatibilityLevel: 1570",
        "\tculture: en-US",
        ""
    ]
    for tbl in tables_list:
        if tbl["name"] == "_Measures":
            continue
        tmdl_lines.append(f"table {tbl['name']}")
        if tbl.get("description"):
            tmdl_lines.append(f"\t// Description: {tbl['description']}")
        for col in tbl.get("columns", []):
            tmdl_lines.append(f"\tcolumn {col['name']}")
            tmdl_lines.append(f"\t\tdataType: {col['dataType']}")
        tmdl_lines.append("")

    for rel in relationships_list:
        tmdl_lines.append(f"relationship '{rel['name']}'")
        tmdl_lines.append(f"\tfromTable: {rel['fromTable']}")
        tmdl_lines.append(f"\tfromColumn: {rel['fromColumn']}")
        tmdl_lines.append(f"\ttoTable: {rel['toTable']}")
        tmdl_lines.append(f"\ttoColumn: {rel['toColumn']}")
        tmdl_lines.append(f"\tcardinality: {rel['cardinality']}")
        if not rel["isActive"]:
            tmdl_lines.append("\tisActive: false")
        tmdl_lines.append("")

    model_tmdl_path = sm_def_dir / "model.tmdl"
    _write_text(model_tmdl_path, "\n".join(tmdl_lines))
    file_paths[f"{project_slug}.SemanticModel/definition/model.tmdl"] = model_tmdl_path

    # ── 6b. <ProjectName>.SemanticModel/model.bim ────────────────────
    bim_tables = []
    for tbl in tables_list:
        bim_cols = []
        for col in tbl.get("columns", []):
            bim_col = {
                "name": col["name"],
                "dataType": _map_data_type_to_bim(col["dataType"]),
                "sourceColumn": col.get("sourceColumn", col["name"]),
            }
            if col.get("sourceColumn") is None:
                bim_col["isHidden"] = True
                bim_col["sourceColumn"] = col["name"]
            bim_cols.append(bim_col)

        bim_measures = []
        for m in tbl.get("measures", []):
            bim_m = {
                "name": m["name"],
                "expression": m["expression"],
            }
            if m.get("description"):
                bim_m["description"] = m["description"]
            bim_measures.append(bim_m)

        bim_tbl = {
            "name": tbl["name"],
            "columns": bim_cols,
            "measures": bim_measures,
            "partitions": [
                {
                    "name": f"{tbl['name']}-partition",
                    "mode": "import",
                    "source": {
                        "type": "m",
                        "expression": f'let\n    Source = ""\nin\n    Source'
                    }
                }
            ]
        }
        if tbl.get("description"):
            bim_tbl["description"] = tbl["description"]
        bim_tables.append(bim_tbl)

    bim_relationships = []
    for rel in relationships_list:
        bim_relationships.append({
            "name": rel["name"],
            "fromTable": rel["fromTable"],
            "fromColumn": rel["fromColumn"],
            "toTable": rel["toTable"],
            "toColumn": rel["toColumn"],
            "crossFilteringBehavior": "oneDirection",
            "isActive": rel["isActive"]
        })

    model_bim = {
        "compatibilityLevel": 1570,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "tables": bim_tables,
            "relationships": bim_relationships,
        }
    }
    model_bim_path = sm_dir / "model.bim"
    _write_json(model_bim_path, model_bim)
    file_paths[f"{project_slug}.SemanticModel/model.bim"] = model_bim_path

    # ── 7. <ProjectName>.SemanticModel/definition/tables/_Measures.tmdl ──
    dax_tmdl_lines = [
        "table _Measures",
        "\tcolumn _placeholder",
        "\t\tdataType: string",
        "\t\tisHidden: true",
        ""
    ]
    for dax in dax_list:
        dax_tmdl_lines.append(f"\tmeasure '{dax['measure_name']}' = {dax['dax_expression']}")
        if dax.get("business_definition"):
            dax_tmdl_lines.append(f"\t\t// Description: {dax['business_definition']}")
        dax_tmdl_lines.append("")

    dax_measures_path = sm_tables_dir / "_Measures.tmdl"
    _write_text(dax_measures_path, "\n".join(dax_tmdl_lines))
    file_paths[f"{project_slug}.SemanticModel/definition/tables/_Measures.tmdl"] = dax_measures_path

    # ── 8. Build report pages and serialize to legacy report.json ────
    pages_list = []
    sections_list = []

    # Check reporting intents to map visual bindings or export tags
    export_pages = []
    for item in intents:
        if item.get("intent") == "data_submission":
            export_pages.append(item.get("requirement", ""))

    page_order = 0
    for page in report_def.get("pages", []):
        page_name = page["page_name"]
        page_slug = _slugify(page_name)
        page_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, page_name))

        visuals_meta = []
        visual_order = 0
        visual_containers = []

        for visual in page.get("visuals", []):
            title = visual.get("title", "")
            visual_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{page_name}_{title}_{visual_order}"))

            # Match against intents to refine types
            matched_intent = ""
            for it in intents:
                if it.get("recommended_visual") == visual.get("visual_type"):
                    matched_intent = it.get("intent", "")
                    break

            mapped_type = map_visual_type(visual.get("visual_type", ""), matched_intent)
            pbi_visual_type = _VISUAL_TYPE_MAP.get(mapped_type, "tableEx")

            # Legacy visual config structure
            # Compile using Report Visual Compiler
            from modules.report_visual_compiler import compile_visual_config
            position = {
                "x": 20 + (visual_order % 2) * 480,
                "y": 20 + (visual_order // 2) * 320,
                "width": 460,
                "height": 300,
                "z": visual_order
            }
            visual_config = compile_visual_config(
                visual_id=visual_id,
                title=title,
                visual_type=mapped_type,
                dimensions=visual.get("dimensions", []),
                measures=visual.get("measures", []),
                position=position
            )

            visual_container = {
                "x": 20 + (visual_order % 2) * 480,
                "y": 20 + (visual_order // 2) * 320,
                "width": 460,
                "height": 300,
                "z": visual_order,
                "config": json.dumps(visual_config, ensure_ascii=False)
            }
            visual_containers.append(visual_container)

            visuals_meta.append({
                "title": title,
                "visual_type": mapped_type,
                "pbi_visual_type": pbi_visual_type,
                "visual_id": visual_id,
                "bindings": {
                    "measures": visual.get("measures", []),
                    "dimensions": visual.get("dimensions", [])
                },
                "business_reason": visual.get("business_reason", "")
            })
            visual_order += 1

        # Section (page) configuration
        section_config = {}
        section = {
            "name": f"Section_{page_id}",
            "displayName": page_name,
            "width": 1280,
            "height": 720,
            "config": json.dumps(section_config),
            "filters": "[]",
            "visualContainers": visual_containers
        }
        sections_list.append(section)

        pages_list.append({
            "page_name": page_name,
            "page_id": page_id,
            "page_slug": page_slug,
            "purpose": page.get("purpose", ""),
            "visuals": visuals_meta,
            "is_export_page": page_name in export_pages
        })
        page_order += 1

    # Write report.json directly under <ProjectName>.Report/
    report_layout = {
        "config": json.dumps({"settings": {}}),
        "layoutOptimization": 0,
        "sections": sections_list
    }
    report_json_path = report_dir / "report.json"
    _write_json(report_json_path, report_layout)
    file_paths[f"{project_slug}.Report/report.json"] = report_json_path

    # ── 9. metadata.json (project root) ──────────────────────────────
    metadata = {
        "project_name": project_name_raw,
        "project_slug": project_slug,
        "generated_at": datetime.now().isoformat(),
        "pbip_spec_version": "1.0",
        "pbir_version": "1.0",
        "stats": {
            "tables_count": len(tables_list) - 1,  # exclude Measures
            "measures_count": len(dax_list),
            "pages_count": len(pages_list),
            "visuals_count": sum(len(p["visuals"]) for p in pages_list),
            "relationships_count": len(relationships_list)
        },
        "contents": {
            "tables": [t["name"] for t in tables_list if t["name"] != "_Measures"],
            "measures": [m["measure_name"] for m in dax_list],
            "pages": [p["page_name"] for p in pages_list]
        }
    }
    metadata_path = _PBIP_DIR / "metadata.json"
    _write_json(metadata_path, metadata)
    file_paths["metadata.json"] = metadata_path

    # ── Create ZIP Archive ───────────────────────────────────────────
    if _ZIP_FILE.exists():
        _ZIP_FILE.unlink()

    with zipfile.ZipFile(_ZIP_FILE, "w", zipfile.ZIP_DEFLATED) as zipf:
        for rel_path, abs_path in file_paths.items():
            zipf.write(abs_path, arcname=rel_path)

    # ── Run Validations ──────────────────────────────────────────────
    validation_result = validate_pbip_project()

    return {
        "is_valid": validation_result["is_valid"],
        "files": {k: {"path": str(v.resolve()), "size_bytes": v.stat().st_size} for k, v in file_paths.items()},
        "zip_path": str(_ZIP_FILE.resolve()),
        "zip_size_bytes": _ZIP_FILE.stat().st_size if _ZIP_FILE.exists() else 0,
        "validation_logs": validation_result["logs"],
        "validation_details": validation_result["details"],
    }


def validate_pbip_project() -> dict:
    """
    Validate the generated PBIP project against the official Power BI Desktop requirements.

    Performs 8 core checks:
    1. PBIP file structure
    2. definition.pbir schema
    3. definition.pbism schema
    4. TMDL syntax validation
    5. report.json structure validation
    6. Semantic model references validation
    7. Relative path validation
    8. Folder naming validation

    Returns a dict with:
        validation_status: str - "Success" | "Warning" | "Failed"
        errors: list[str] - Critical compatibility blockers
        warnings: list[str] - Non-blocking warnings
        power_bi_compatible: bool - True if 0 critical errors
        missing_artifacts: list[str] - List of missing required files/folders
        invalid_references: list[str] - List of reference or path mismatches
        recommended_fixes: list[str] - List of fixes to achieve full compatibility
        is_valid: bool - Deprecated, mapped to power_bi_compatible for compatibility
        details: list[dict] - Per-file details
        logs: list[str] - Log messages
    """
    project_slug = get_project_slug()
    req_files = get_required_files(project_slug)

    errors = []
    warnings = []
    missing_artifacts = []
    invalid_references = []
    recommended_fixes = []
    details = []
    logs = []

    # ── 1. PBIP File Structure Check ─────────────────────────────────
    for rel_path, description in req_files:
        abs_path = _PBIP_DIR / rel_path
        exists = abs_path.exists()
        size = abs_path.stat().st_size if exists else 0
        is_empty = exists and size == 0

        if not exists:
            status = "missing"
            errors.append(f"Missing required file: `{rel_path}`")
            missing_artifacts.append(rel_path)
            logs.append(f"MISSING: `{rel_path}` - {description}")
            recommended_fixes.append(f"Generate the missing file `{rel_path}` in the project directory.")
        elif is_empty:
            status = "empty"
            errors.append(f"Empty required file: `{rel_path}`")
            logs.append(f"EMPTY: `{rel_path}` - {description}")
            recommended_fixes.append(f"Populate the empty required file `{rel_path}` with valid metadata.")
        else:
            status = "valid"
            logs.append(f"FOUND: `{rel_path}` ({size / 1024:.1f} KB)")

        details.append({
            "file": rel_path,
            "description": description,
            "status": status,
            "exists": exists,
            "size_bytes": size,
            "abs_path": str(abs_path.resolve()) if exists else None,
        })

    # ── 2. definition.pbir Schema Check ──────────────────────────────
    pbir_path = _PBIP_DIR / f"{project_slug}.Report" / "definition.pbir"
    if pbir_path.exists():
        try:
            pbir = json.loads(pbir_path.read_text(encoding="utf-8"))
            if pbir.get("version") != "1.0":
                warnings.append(f"definition.pbir version is '{pbir.get('version')}', expected '1.0' for legacy format compatibility.")
                recommended_fixes.append("Change version to '1.0' in `definition.pbir` to match legacy report layout expectations.")
            
            if "datasetReference" not in pbir:
                errors.append("`definition.pbir` is missing `datasetReference` property.")
                invalid_references.append("definition.pbir -> datasetReference")
                recommended_fixes.append("Add a valid `datasetReference` object to `definition.pbir` pointing to the Semantic Model.")
            else:
                ds_ref = pbir["datasetReference"]
                if not isinstance(ds_ref, dict):
                    errors.append("`datasetReference` in `definition.pbir` must be a JSON object.")
                    recommended_fixes.append("Change `datasetReference` structure in `definition.pbir` to a valid object.")
                elif "byPath" not in ds_ref:
                    errors.append("`datasetReference` in `definition.pbir` is missing `byPath` property.")
                    recommended_fixes.append("Add `byPath` sub-object under `datasetReference` in `definition.pbir`.")
                else:
                    by_path = ds_ref["byPath"]
                    if not isinstance(by_path, dict) or "path" not in by_path:
                        errors.append("`datasetReference.byPath` in `definition.pbir` is missing `path` property.")
                        recommended_fixes.append("Add relative path connection string in `datasetReference.byPath.path`.")
            logs.append("PBIR: definition.pbir schema validated")
        except json.JSONDecodeError:
            errors.append("`definition.pbir` is not valid JSON.")
            recommended_fixes.append("Fix JSON syntax errors in `definition.pbir`.")
        except Exception as e:
            errors.append(f"Failed to validate `definition.pbir`: {str(e)}")

    # ── 3. definition.pbism Schema Check ─────────────────────────────
    pbism_path = _PBIP_DIR / f"{project_slug}.SemanticModel" / "definition.pbism"
    if pbism_path.exists():
        try:
            pbism = json.loads(pbism_path.read_text(encoding="utf-8"))
            if pbism.get("version") != "1.0":
                warnings.append(f"definition.pbism version is '{pbism.get('version')}', expected '1.0'.")
                recommended_fixes.append("Set version to '1.0' in `definition.pbism`.")
            if "settings" not in pbism:
                warnings.append("`definition.pbism` is missing `settings` configuration property.")
                recommended_fixes.append("Add a `settings` object parameter to `definition.pbism`.")
            logs.append("PBISM: definition.pbism schema validated")
        except json.JSONDecodeError:
            errors.append("`definition.pbism` is not valid JSON.")
            recommended_fixes.append("Fix JSON syntax errors in `definition.pbism`.")

    # ── 4. TMDL Syntax Validation ────────────────────────────────────
    model_tmdl = _PBIP_DIR / f"{project_slug}.SemanticModel" / "definition" / "model.tmdl"
    if model_tmdl.exists():
        try:
            content = model_tmdl.read_text(encoding="utf-8")
            if "model Model" not in content:
                errors.append("`model.tmdl` is missing the `model Model` declaration header.")
                recommended_fixes.append("Add `model Model` header at line 1 in `model.tmdl`.")
            
            # TMDL strict tab-indentation rule validation
            lines = content.splitlines()
            space_indented = [i + 1 for i, l in enumerate(lines) if l.startswith(" ")]
            if space_indented:
                errors.append(f"`model.tmdl` uses space indentation on line(s): {space_indented[:5]}. TMDL requires tabs.")
                recommended_fixes.append("Convert space indentation to tab indentation in `model.tmdl`.")
            
            # Check for naming collisions or duplicate headers
            relationships = []
            for line in lines:
                if line.strip().startswith("relationship"):
                    rel_name = line.split("relationship")[-1].strip().strip("'\"")
                    relationships.append(rel_name)
            
            duplicates = set([x for x in relationships if relationships.count(x) > 1])
            if duplicates:
                errors.append(f"`model.tmdl` contains duplicate relationship names: {duplicates}. Relationship names must be unique.")
                recommended_fixes.append("Ensure each relationship block in `model.tmdl` uses a unique identifier string.")
            
            logs.append("TMDL: model.tmdl structure and syntax verified")
        except Exception as e:
            errors.append(f"Failed to validate TMDL syntax in `model.tmdl`: {str(e)}")

    measures_tmdl = _PBIP_DIR / f"{project_slug}.SemanticModel" / "definition" / "tables" / "_Measures.tmdl"
    if measures_tmdl.exists():
        try:
            content = measures_tmdl.read_text(encoding="utf-8")
            if "table _Measures" not in content:
                errors.append("`_Measures.tmdl` is missing `table _Measures` declaration header.")
                recommended_fixes.append("Add `table _Measures` header at line 1 in `_Measures.tmdl`.")
            
            lines = content.splitlines()
            space_indented = [i + 1 for i, l in enumerate(lines) if l.startswith(" ")]
            if space_indented:
                errors.append(f"`_Measures.tmdl` uses space indentation on line(s): {space_indented[:5]}. TMDL requires tabs.")
                recommended_fixes.append("Convert space indentation to tab indentation in `_Measures.tmdl`.")
            logs.append("TMDL: _Measures.tmdl structure and syntax verified")
        except Exception as e:
            errors.append(f"Failed to validate TMDL syntax in `_Measures.tmdl`: {str(e)}")

    # ── 5. report.json Structure Validation ──────────────────────────
    report_json = _PBIP_DIR / f"{project_slug}.Report" / "report.json"
    if report_json.exists():
        try:
            layout = json.loads(report_json.read_text(encoding="utf-8"))
            if "sections" not in layout:
                errors.append("`report.json` is missing the `sections` page array property.")
                recommended_fixes.append("Add a `sections` array to `report.json` to define pages.")
            else:
                sections = layout["sections"]
                if not isinstance(sections, list):
                    errors.append("`sections` property in `report.json` must be an array.")
                    recommended_fixes.append("Change `sections` in `report.json` to be a valid JSON array.")
                else:
                    for s_idx, sec in enumerate(sections):
                        sec_name = sec.get("displayName", f"Page {s_idx + 1}")
                        if "name" not in sec:
                            errors.append(f"Page '{sec_name}' is missing the unique `name` GUID property in `report.json`.")
                            recommended_fixes.append(f"Add unique `name` property to Page '{sec_name}' in `report.json`.")
                        if "visualContainers" not in sec:
                            errors.append(f"Page '{sec_name}' is missing `visualContainers` array.")
                            recommended_fixes.append(f"Add `visualContainers` array to Page '{sec_name}' in `report.json`.")
                        else:
                            vcontainers = sec["visualContainers"]
                            if not isinstance(vcontainers, list):
                                errors.append(f"`visualContainers` for Page '{sec_name}' must be an array.")
                            else:
                                for v_idx, vc in enumerate(vcontainers):
                                    if "config" not in vc:
                                        errors.append(f"Visual index {v_idx} on Page '{sec_name}' is missing `config` string.")
                                        recommended_fixes.append(f"Add serialized `config` string to Visual index {v_idx} on Page '{sec_name}'.")
                                    else:
                                        try:
                                            json.loads(vc["config"])
                                        except json.JSONDecodeError:
                                            errors.append(f"Visual index {v_idx} config on Page '{sec_name}' is not valid serialized JSON.")
                                            recommended_fixes.append(f"Ensure the visual `config` string on Page '{sec_name}' is a valid JSON-encoded string.")
            logs.append("REPORT: report.json structure validated")
        except json.JSONDecodeError:
            errors.append("`report.json` is not valid JSON.")
            recommended_fixes.append("Ensure `report.json` contains valid JSON layout syntax.")
        except Exception as e:
            errors.append(f"Failed to read/parse `report.json`: {str(e)}")

    # ── 6. Semantic Model References Validation ──────────────────────
    if pbir_path.exists():
        try:
            pbir = json.loads(pbir_path.read_text(encoding="utf-8"))
            ds_ref = pbir.get("datasetReference", {})
            by_path = ds_ref.get("byPath", {})
            path_val = by_path.get("path", "")
            
            expected_ref_path = f"../{project_slug}.SemanticModel"
            if path_val != expected_ref_path:
                errors.append(f"`definition.pbir` references model at '{path_val}', expected '{expected_ref_path}'.")
                invalid_references.append("definition.pbir -> datasetReference.byPath.path")
                recommended_fixes.append(f"Update relative path in `definition.pbir` to point to '{expected_ref_path}'.")
            else:
                logs.append("REFERENCES: Semantic model path reference verified")
        except Exception:
            pass

    # ── 7. Relative Path Validation ──────────────────────────────────
    report_folder_abs = _PBIP_DIR / f"{project_slug}.Report"
    if pbir_path.exists():
        try:
            pbir = json.loads(pbir_path.read_text(encoding="utf-8"))
            ds_ref = pbir.get("datasetReference", {})
            by_path = ds_ref.get("byPath", {})
            path_val = by_path.get("path", "")
            
            if path_val:
                resolved_abs_path = (report_folder_abs / path_val).resolve()
                expected_abs_path = (_PBIP_DIR / f"{project_slug}.SemanticModel").resolve()
                
                if resolved_abs_path != expected_abs_path:
                    errors.append(f"Resolved SemanticModel path '{resolved_abs_path}' does not match expected '{expected_abs_path}'.")
                    invalid_references.append("Relative path resolution mismatch")
                    recommended_fixes.append(f"Ensure relative path in `definition.pbir` resolves to '{expected_abs_path}'.")
                elif not resolved_abs_path.exists():
                    errors.append(f"SemanticModel folder does not exist at resolved relative path: '{resolved_abs_path}'.")
                    missing_artifacts.append(f"{project_slug}.SemanticModel")
                    recommended_fixes.append(f"Generate or copy the semantic model folder to '{resolved_abs_path}'.")
                else:
                    logs.append("PATHS: Relative connection path resolved successfully")
        except Exception as e:
            errors.append(f"Failed to validate relative path resolution: {str(e)}")

    # ── 8. Folder Naming Validation ──────────────────────────────────
    pbip_files = list(_PBIP_DIR.glob("*.pbip"))
    if not pbip_files:
        errors.append("No `.pbip` entry point file found in the project root.")
        recommended_fixes.append(f"Create the project entry point file `{project_slug}.pbip`.")
    else:
        for pbip_f in pbip_files:
            prefix = pbip_f.stem
            report_folder = _PBIP_DIR / f"{prefix}.Report"
            sm_folder = _PBIP_DIR / f"{prefix}.SemanticModel"
            
            if not report_folder.exists():
                errors.append(f"Report folder name mismatch. Expected folder: `{prefix}.Report`.")
                missing_artifacts.append(f"{prefix}.Report")
                recommended_fixes.append(f"Rename the report folder to `{prefix}.Report`.")
            if not sm_folder.exists():
                errors.append(f"Semantic model folder name mismatch. Expected folder: `{prefix}.SemanticModel`.")
                missing_artifacts.append(f"{prefix}.SemanticModel")
                recommended_fixes.append(f"Rename the semantic model folder to `{prefix}.SemanticModel`.")
        logs.append("NAMING: Folder prefix names verified successfully")

    # ── Validate ZIP Archive ─────────────────────────────────────────
    if _ZIP_FILE.exists():
        try:
            z_size = _ZIP_FILE.stat().st_size
            with zipfile.ZipFile(_ZIP_FILE, "r") as zf:
                zip_names = set(zf.namelist())
            missing_in_zip = []
            for rel_path, _ in req_files:
                if rel_path not in zip_names:
                    missing_in_zip.append(rel_path)
            if missing_in_zip:
                errors.append(f"ZIP Archive is missing files: {missing_in_zip}")
                for m in missing_in_zip:
                    logs.append(f"ZIP MISSING: `{m}`")
            else:
                logs.append(f"ZIP: Archive validated - all {len(req_files)} core files present ({z_size / 1024:.1f} KB)")
        except zipfile.BadZipFile:
            errors.append("ZIP Archive is corrupt (BadZipFile).")
            recommended_fixes.append("Re-compile the PBIP project to rebuild a valid ZIP archive.")
        except Exception as e:
            errors.append(f"ZIP validation failed: {str(e)}")
    else:
        errors.append("ZIP Archive `pbip_project.zip` not found.")
        recommended_fixes.append("Compile the project to generate `pbip_project.zip`.")

    # ── 9. Relationship Validation Check ──────────────────────────────
    if _ANALYTICS_MODEL_FILE.exists():
        try:
            from modules.relationship_validator import validate_relationships
            with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
                model_data = json.load(f)
            rel_issues = validate_relationships(model_data)
            
            for issue in rel_issues:
                rel = issue["relationship"]
                status_val = issue["status"]
                desc = issue["issue"]
                rec = issue["recommendation"]
                
                log_msg = f"RELATIONSHIP {status_val.upper()}: `{rel}` - {desc}"
                logs.append(log_msg)
                
                if status_val == "Error":
                    errors.append(f"Relationship error: {desc} (Path: {rel})")
                    recommended_fixes.append(f"For '{rel}': {rec}")
                elif status_val == "Warning":
                    warnings.append(f"Relationship warning: {desc} (Path: {rel})")
                    recommended_fixes.append(f"For '{rel}': {rec}")
            
            logs.append("RELATIONSHIPS: Analytics model relationship check completed")
        except Exception as e:
            errors.append(f"Failed to perform relationship validation: {str(e)}")

    # ── 10. Report Layout Validation Check ────────────────────────────
    try:
        from modules.report_layout_validator import validate_report_layout_from_files
        layout_issues = validate_report_layout_from_files()
        
        for issue in layout_issues:
            v_title = issue.get("visual", "Unknown")
            status_val = issue.get("status", "Warning")
            desc = issue.get("issue", "")
            rec = issue.get("recommendation", "")
            
            log_msg = f"LAYOUT {status_val.upper()}: `{v_title}` - {desc}"
            logs.append(log_msg)
            
            if status_val == "Error":
                errors.append(f"Layout error: {desc} (Visual: {v_title})")
                recommended_fixes.append(f"For '{v_title}': {rec}")
            elif status_val == "Warning":
                warnings.append(f"Layout warning: {desc} (Visual: {v_title})")
                recommended_fixes.append(f"For '{v_title}': {rec}")
                
        logs.append("LAYOUT: Report layout validation completed")
    except Exception as e:
        warnings.append(f"Layout warning: Failed to perform report layout validation: {str(e)}")

    # ── Determine Overall Status ─────────────────────────────────────
    power_bi_compatible = len(errors) == 0
    if not power_bi_compatible:
        validation_status = "Failed"
    elif len(warnings) > 0:
        validation_status = "Warning"
    else:
        validation_status = "Success"

    return {
        "validation_status": validation_status,
        "errors": errors,
        "warnings": warnings,
        "power_bi_compatible": power_bi_compatible,
        "missing_artifacts": missing_artifacts,
        "invalid_references": invalid_references,
        "recommended_fixes": recommended_fixes,
        "is_valid": power_bi_compatible,  # Mapped for compatibility
        "details": details,
        "logs": logs,
    }


# ── Private Helpers ──────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    """Write a dict as pretty-printed JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_text(path: Path, text: str) -> None:
    """Write plain text content."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _map_data_type_to_bim(data_type: str) -> str:
    """Map analytics model data types to TOM/TMSL data types for model.bim."""
    dt_lower = data_type.lower()
    mapping = {
        "string": "string",
        "integer": "int64",
        "int": "int64",
        "int64": "int64",
        "decimal": "double",
        "double": "double",
        "float": "double",
        "boolean": "boolean",
        "bool": "boolean",
        "date": "dateTime",
        "datetime": "dateTime",
        "currency": "decimal",
    }
    return mapping.get(dt_lower, "string")
