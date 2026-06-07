"""
Report Layout Validator Module.

Validates report.json against the semantic model (model.bim) before PBIP packaging.
Performs 7 checks to ensure layout and semantic bindings are valid and in sync.
"""

import json
import difflib
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from modules.file_manager import OUTPUT_DIR, KNOWLEDGE_DIR
from modules.pbip_generator import compile_pbip_project, validate_pbip_project


def validate_report_layout(
    report_data: Dict[str, Any],
    model_data: Dict[str, Any],
    report_def: Dict[str, Any]
) -> List[Dict[str, str]]:
    """
    Audit report.json against model.bim and the report definition spec.

    Args:
        report_data: The dictionary loaded from report.json.
        model_data: The dictionary loaded from model.bim.
        report_def: The dictionary loaded from report_definition.json.

    Returns:
        A list of validation issues found:
        {
            "visual": str,          # Name/title of the visual
            "status": str,          # "Error" | "Warning"
            "issue": str,           # Issue description
            "recommendation": str   # Recommendation to fix the issue
        }
    """
    issues = []

    # ── 1. Map tables, columns, and measures from model.bim ───────────
    tables_dict = {}  # table_name -> set of column_names
    measures_set = set()  # set of measure_names

    tables_list = model_data.get("model", {}).get("tables", [])
    for t in tables_list:
        t_name = t.get("name", "")
        cols = {c.get("name", "") for c in t.get("columns", [])}
        tables_dict[t_name] = cols
        
        # Measures can be located in any table in model.bim
        for m in t.get("measures", []):
            measures_set.add(m.get("name", ""))

    # ── 2. Run Checks ──────────────────────────────────────────────────
    # Map visualContainer titles from report.json to check for orphans
    report_visual_titles = set()
    report_visual_by_title = {}

    sections = report_data.get("sections", [])
    for sec in sections:
        page_name = sec.get("displayName", "")
        containers = sec.get("visualContainers", [])
        for vc in containers:
            config_str = vc.get("config", "{}")
            try:
                config = json.loads(config_str)
                v_name = config.get("name", "")
                
                # Try to extract the custom title
                title_text = ""
                vc_title_objs = config.get("singleVisual", {}).get("vcObjects", {}).get("title", [])
                if vc_title_objs:
                    title_text = vc_title_objs[0].get("properties", {}).get("text", {}).get("expr", {}).get("Literal", {}).get("Value", "")
                    title_text = title_text.strip("'\"")
                
                v_title = title_text or v_name
                report_visual_titles.add(v_title)
                
                v_type = config.get("singleVisual", {}).get("visualType", "")
                report_visual_by_title[v_title] = {
                    "id": v_name,
                    "type": v_type,
                    "page": page_name
                }
                
                # Check: Reject visuals with empty projections or prototypeQuery
                if v_type not in ["textbox", "image"]:
                    single_visual = config.get("singleVisual", {})
                    projections = single_visual.get("projections", {})
                    prototype_query = single_visual.get("prototypeQuery", {})
                    
                    if not projections:
                        issues.append({
                            "visual": v_title,
                            "status": "Error",
                            "issue": f"Visual '{v_title}' has empty projections definition.",
                            "recommendation": "Compile the report with the Report Visual Compiler to bind fields."
                        })
                    if not prototype_query or not prototype_query.get("Select"):
                        issues.append({
                            "visual": v_title,
                            "status": "Error",
                            "issue": f"Visual '{v_title}' has empty prototypeQuery schema definition.",
                            "recommendation": "Compile the report with the Report Visual Compiler to populate prototype queries."
                        })
            except Exception:
                pass

    # Gather spec visuals to match with layout
    spec_visual_titles = set()
    spec_visuals = []
    
    pages = report_def.get("pages", [])
    for p in pages:
        p_name = p.get("page_name", "")
        for v in p.get("visuals", []):
            v_title = v.get("title", "")
            spec_visual_titles.add(v_title)
            spec_visuals.append({
                **v,
                "page": p_name
            })

    # Check 5: Detect Orphan Visual References
    # (a) Visual in spec but missing from layout
    for v_title in spec_visual_titles:
        if v_title not in report_visual_titles:
            issues.append({
                "visual": v_title,
                "status": "Error",
                "issue": f"Visual '{v_title}' is defined in the report spec but is missing from report.json layout.",
                "recommendation": "Compile the PBIP project to regenerate the report layout."
            })

    # (b) Visual in layout but missing from spec
    for v_title, info in report_visual_by_title.items():
        # Exclude common system/helper visual elements if any
        if v_title not in spec_visual_titles and info["type"] not in ["textbox", "image"]:
            issues.append({
                "visual": v_title,
                "status": "Warning",
                "issue": f"Visual container '{v_title}' exists in report.json layout but is not defined in the report spec.",
                "recommendation": "Remove orphan visual from layout, or declare it in report_definition.json."
            })

    # Validate each visual spec against the model
    for v in spec_visuals:
        title = v.get("title", "")
        v_type = v.get("visual_type", "")
        dims = v.get("dimensions", [])
        meas = v.get("measures", [])

        # Check 1, 2, 3, 6: Bindings Validation (Fields, Tables, Measures, Stale check)
        for d_field in dims:
            if "." in d_field:
                tbl, col = d_field.split(".", 1)
                # Check 2: Table exists
                if tbl not in tables_dict:
                    issues.append({
                        "visual": title,
                        "status": "Error",
                        "issue": f"Table '{tbl}' referenced in dimension '{d_field}' does not exist in model.bim.",
                        "recommendation": f"Verify if '{tbl}' was renamed or omitted during star schema generation."
                    })
                # Check 1: Field exists in table
                elif col not in tables_dict[tbl]:
                    issues.append({
                        "visual": title,
                        "status": "Error",
                        "issue": f"Column '{col}' in table '{tbl}' does not exist in model.bim.",
                        "recommendation": f"Verify if column '{col}' is named correctly in table '{tbl}'."
                    })
            else:
                # Column referenced without table name
                found = False
                for tbl, cols in tables_dict.items():
                    if d_field in cols:
                        found = True
                        break
                if not found:
                    issues.append({
                        "visual": title,
                        "status": "Error",
                        "issue": f"Dimension field '{d_field}' does not exist in any table of model.bim.",
                        "recommendation": f"Specify field with table prefix (e.g. Table.Field) and verify spelling."
                    })

        for m_field in meas:
            # Check 3: Measure exists
            if m_field not in measures_set:
                # Also check if it's referenced as Table.Measure
                m_clean = m_field.split(".", 1)[1] if "." in m_field else m_field
                if m_clean not in measures_set:
                    issues.append({
                        "visual": title,
                        "status": "Error",
                        "issue": f"Measure '{m_field}' does not exist in model.bim.",
                        "recommendation": f"Verify if the measure '{m_field}' was compiled in dax_artifacts.json."
                    })

        # Check 4: Visual type required properties
        # card / gauge constraints
        if v_type in ["card", "gauge"]:
            if len(meas) != 1:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Visual type '{v_type}' contains {len(meas)} measures. Power BI standard requires exactly 1 measure.",
                    "recommendation": "Adjust measures list to contain exactly one measure."
                })
            if len(dims) > 0:
                issues.append({
                    "visual": title,
                    "status": "Warning",
                    "issue": f"Visual type '{v_type}' contains {len(dims)} dimensions. Cards/gauges do not display dimensions.",
                    "recommendation": "Remove dimensions from the card visual definition."
                })
        # charts requirements
        elif v_type in ["line_chart", "bar_chart", "donut_chart", "pie_chart", "column_chart"]:
            if len(dims) < 1:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Visual chart '{v_type}' contains 0 dimensions. Charts require at least 1 axis/legend dimension.",
                    "recommendation": "Add at least one dimension (e.g. DimDate.month_name) to the visual."
                })
            if len(meas) < 1:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Visual chart '{v_type}' contains 0 measures. Charts require at least 1 metric measure to plot.",
                    "recommendation": "Add at least one measure (e.g. [Total Determinations]) to the visual."
                })
        # matrix requirements
        elif v_type == "matrix":
            if len(dims) < 1:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Matrix visual requires at least 1 dimension to define rows/columns.",
                    "recommendation": "Add row/column dimensions."
                })
        # table requirements
        elif v_type == "table":
            if len(dims) == 0 and len(meas) == 0:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Table visual contains 0 fields. A table requires at least 1 column or measure to display.",
                    "recommendation": "Add columns or measures to the table visual."
                })

    return issues


def auto_correct_report_layout() -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """
    Perform remapping of invalid tables, columns, and measures in report_definition.json,
    synchronize with model.bim, recompile PBIP, and rerun validation.

    Returns:
        applied_fixes: List of fixes applied:
        {
            "visual": str,
            "issue": str,
            "fix_applied": str
        }
        validation_results: Dict containing the layout validation results.
    """
    from modules.pbip_generator import get_project_slug
    import shutil

    report_def_path = OUTPUT_DIR / "report_definition.json"
    analytics_model_path = OUTPUT_DIR / "analytics_model.json"
    dax_path = OUTPUT_DIR / "dax_artifacts.json"
    measures_path = OUTPUT_DIR / "measures.json"

    if not report_def_path.exists() or not analytics_model_path.exists():
        raise FileNotFoundError("Missing report_definition.json or analytics_model.json to auto-correct.")

    with open(report_def_path, "r", encoding="utf-8") as f:
        report_def = json.load(f)

    with open(analytics_model_path, "r", encoding="utf-8") as f:
        analytics_model = json.load(f)

    # ── 1. Map columns and measures ───────────────────────────────────
    # Map column names in analytics model to their tables
    # col_name -> list of table_names containing this column
    model_columns_map = {}
    valid_tables = set()
    for t in analytics_model.get("fact_tables", []) + analytics_model.get("dimension_tables", []):
        t_name = t.get("name", "")
        valid_tables.add(t_name)
        for col in t.get("columns", []):
            c_name = col.get("name", "")
            if c_name not in model_columns_map:
                model_columns_map[c_name] = []
            model_columns_map[c_name].append(t_name)

    # Gather available measures in the compiled artifacts
    available_measures = set()
    if dax_path.exists():
        with open(dax_path, "r", encoding="utf-8") as f:
            dax_list = json.load(f)
            available_measures.update(m.get("measure_name", "") for m in dax_list)
    else:
        # Fallback to report_definition measures spec
        available_measures.update(m.get("name", "") for m in report_def.get("measures", []))

    applied_fixes = []

    # Helper to clean up table name replacements
    table_replacements = {} # old_table -> new_table

    # ── 2. Fix visuals field bindings ──────────────────────────────────
    pages = report_def.get("pages", [])
    for p in pages:
        for v in p.get("visuals", []):
            title = v.get("title", "")
            v_type = v.get("visual_type", "")
            
            # (a) Check dimensions
            corrected_dims = []
            for d_field in v.get("dimensions", []):
                if "." in d_field:
                    tbl, col = d_field.split(".", 1)
                    if tbl not in valid_tables:
                        # Remap table name based on column existence
                        if col in model_columns_map:
                            new_tbl = model_columns_map[col][0] # Pick first table containing this column
                            corrected_dims.append(f"{new_tbl}.{col}")
                            table_replacements[tbl] = new_tbl
                            applied_fixes.append({
                                "visual": title,
                                "issue": f"Dimension references missing table '{tbl}' in field '{d_field}'.",
                                "fix_applied": f"Remapped field to '{new_tbl}.{col}' (found column in '{new_tbl}')."
                            })
                        else:
                            # Let's see if we can find a table that is similar
                            similar_tables = difflib.get_close_matches(tbl, list(valid_tables), n=1, cutoff=0.5)
                            if similar_tables:
                                new_tbl = similar_tables[0]
                                corrected_dims.append(f"{new_tbl}.{col}")
                                table_replacements[tbl] = new_tbl
                                applied_fixes.append({
                                    "visual": title,
                                    "issue": f"Dimension references missing table '{tbl}' in field '{d_field}'.",
                                    "fix_applied": f"Remapped table '{tbl}' to '{new_tbl}' (similar table name)."
                                })
                            else:
                                corrected_dims.append(d_field) # keep original if no match
                    else:
                        corrected_dims.append(d_field)
                else:
                    # Column without table prefix
                    if d_field not in model_columns_map:
                        # Try case insensitive match or fuzzy match
                        similar_cols = difflib.get_close_matches(d_field, list(model_columns_map.keys()), n=1, cutoff=0.6)
                        if similar_cols:
                            new_col = similar_cols[0]
                            new_tbl = model_columns_map[new_col][0]
                            corrected_dims.append(f"{new_tbl}.{new_col}")
                            applied_fixes.append({
                                "visual": title,
                                "issue": f"Field '{d_field}' is missing from the model.",
                                "fix_applied": f"Remapped to '{new_tbl}.{new_col}' (closest matching column)."
                            })
                        else:
                            corrected_dims.append(d_field)
                    else:
                        new_tbl = model_columns_map[d_field][0]
                        corrected_dims.append(f"{new_tbl}.{d_field}")
                        applied_fixes.append({
                            "visual": title,
                            "issue": f"Field '{d_field}' is missing table prefix.",
                            "fix_applied": f"Added prefix: '{new_tbl}.{d_field}'."
                        })
            v["dimensions"] = corrected_dims

            # (b) Check measures list
            corrected_meas = []
            for m_field in v.get("measures", []):
                m_clean = m_field.split(".", 1)[1] if "." in m_field else m_field
                if m_clean not in available_measures:
                    # Find closest matching measure in the model
                    similar_measures = difflib.get_close_matches(m_clean, list(available_measures), n=1, cutoff=0.4)
                    if similar_measures:
                        new_measure = similar_measures[0]
                        corrected_meas.append(new_measure)
                        applied_fixes.append({
                            "visual": title,
                            "issue": f"Measure '{m_clean}' is missing from the compiled semantic model.",
                            "fix_applied": f"Remapped measure '{m_clean}' to '{new_measure}'."
                        })
                    else:
                        corrected_meas.append(m_field)
                else:
                    corrected_meas.append(m_clean)
            v["measures"] = corrected_meas

            # (c) Validate visual properties and fix constraints
            if v_type in ["card", "gauge"]:
                if len(v["measures"]) > 1:
                    orig_count = len(v["measures"])
                    v["measures"] = [v["measures"][0]]
                    applied_fixes.append({
                        "visual": title,
                        "issue": f"Visual type '{v_type}' contains {orig_count} measures (standard limit: 1).",
                        "fix_applied": f"Truncated measures list to only use the first measure: '{v['measures'][0]}'."
                    })
                if len(v.get("dimensions", [])) > 0:
                    v["dimensions"] = []
                    applied_fixes.append({
                        "visual": title,
                        "issue": f"Visual type '{v_type}' contains dimensions.",
                        "fix_applied": "Removed dimensions from visual definition as cards/gauges do not display them."
                    })
            elif v_type in ["line_chart", "bar_chart", "donut_chart", "pie_chart", "column_chart"]:
                if len(v.get("dimensions", [])) == 0:
                    # Add DimDate.month_name as default axis if it exists
                    default_dim = "DimDate.month_name"
                    if "DimDate" in valid_tables and "month_name" in model_columns_map.get("month_name", []):
                        v["dimensions"] = [default_dim]
                    else:
                        # Find any dimension column
                        found_dim = None
                        for tbl in valid_tables:
                            if tbl.startswith("Dim") and tbl != "DimDate":
                                cols = list(model_columns_map.keys())
                                # Pick first non-key column in dimension
                                for c in cols:
                                    if tbl in model_columns_map[c] and not c.endswith("_key") and not c.endswith("_id"):
                                        found_dim = f"{tbl}.{c}"
                                        break
                            if found_dim:
                                break
                        v["dimensions"] = [found_dim] if found_dim else []
                    
                    dim_desc = v["dimensions"][0] if v["dimensions"] else "None available"
                    applied_fixes.append({
                        "visual": title,
                        "issue": f"Chart visual '{v_type}' is missing required dimension bindings.",
                        "fix_applied": f"Assigned default dimension: '{dim_desc}'."
                    })
                if len(v.get("measures", [])) == 0:
                    # Assign first available measure
                    if available_measures:
                        v["measures"] = [list(available_measures)[0]]
                        applied_fixes.append({
                            "visual": title,
                            "issue": f"Chart visual '{v_type}' is missing required measure metrics.",
                            "fix_applied": f"Assigned first available measure: '{v['measures'][0]}'."
                        })

    # ── 3. Remap filters in report_definition ──────────────────────────
    if "filters" in report_def:
        for filt in report_def["filters"]:
            f_field = filt.get("field", "")
            if "." in f_field:
                tbl, col = f_field.split(".", 1)
                if tbl not in valid_tables:
                    if col in model_columns_map:
                        new_tbl = model_columns_map[col][0]
                        filt["field"] = f"{new_tbl}.{col}"
                        applied_fixes.append({
                            "visual": f"Filter: {filt.get('name', 'Unnamed')}",
                            "issue": f"Filter references missing table '{tbl}'.",
                            "fix_applied": f"Remapped to '{new_tbl}.{col}'."
                        })

    # ── 4. Synchronize dax_artifacts.json if tables were remapped ─────
    # E.g. replace FactObservation with FactDetermination in expressions
    if dax_path.exists() and table_replacements:
        try:
            with open(dax_path, "r", encoding="utf-8") as f:
                dax_list = json.load(f)
            
            dax_modified = False
            for dax in dax_list:
                expr = dax.get("dax_expression", "")
                for old_t, new_t in table_replacements.items():
                    if old_t in expr:
                        expr = expr.replace(old_t, new_t)
                        dax["dax_expression"] = expr
                        dax_modified = True
                        applied_fixes.append({
                            "visual": f"DAX Measure: {dax['measure_name']}",
                            "issue": f"DAX expression references missing table '{old_t}'.",
                            "fix_applied": f"Updated DAX reference from '{old_t}' to '{new_t}'."
                        })
            
            if dax_modified:
                with open(dax_path, "w", encoding="utf-8") as f:
                    json.dump(dax_list, f, indent=2)
        except Exception:
            pass

    # Synchronize measures.json if tables were remapped
    if measures_path.exists() and table_replacements:
        try:
            with open(measures_path, "r", encoding="utf-8") as f:
                m_list = json.load(f)
            
            m_modified = False
            for m in m_list:
                # 1. Update dax_expression if it exists
                expr = m.get("dax_expression", "")
                if expr:
                    for old_t, new_t in table_replacements.items():
                        if old_t in expr:
                            expr = expr.replace(old_t, new_t)
                            m["dax_expression"] = expr
                            m_modified = True
                
                # 2. Update formula_description
                formula_desc = m.get("formula_description", "")
                if formula_desc:
                    for old_t, new_t in table_replacements.items():
                        if old_t in formula_desc:
                            formula_desc = formula_desc.replace(old_t, new_t)
                            m["formula_description"] = formula_desc
                            m_modified = True
                            
                # 3. Update source_tables list
                src_tables = m.get("source_tables", [])
                if isinstance(src_tables, list):
                    new_src_tables = []
                    tbl_changed = False
                    for tbl in src_tables:
                        if tbl in table_replacements:
                            new_src_tables.append(table_replacements[tbl])
                            tbl_changed = True
                        else:
                            new_src_tables.append(tbl)
                    if tbl_changed:
                        m["source_tables"] = new_src_tables
                        m_modified = True
                        
                # 4. Update home_table if it exists
                ht = m.get("home_table", "")
                if ht in table_replacements:
                    m["home_table"] = table_replacements[ht]
                    m_modified = True
            
            if m_modified:
                with open(measures_path, "w", encoding="utf-8") as f:
                    json.dump(m_list, f, indent=2)
        except Exception:
            pass

    # ── 5. Save the updated report_definition.json and Recompile ──────
    with open(report_def_path, "w", encoding="utf-8") as f:
        json.dump(report_def, f, indent=2)

    # Compile the PBIP project (this recreates report.json and model.bim)
    compile_result = compile_pbip_project()

    # Rerun validation
    project_slug = get_project_slug()
    report_json_path = OUTPUT_DIR / "pbip" / f"{project_slug}.Report" / "report.json"
    model_bim_path = OUTPUT_DIR / "pbip" / f"{project_slug}.SemanticModel" / "model.bim"

    with open(report_json_path, "r", encoding="utf-8") as f:
        corrected_report = json.load(f)
    with open(model_bim_path, "r", encoding="utf-8") as f:
        corrected_model = json.load(f)

    new_issues = validate_report_layout(corrected_report, corrected_model, report_def)

    return applied_fixes, {
        "status": "Success" if not new_issues else "Warning",
        "issues": new_issues,
        "compile_result": compile_result
    }


def validate_report_layout_from_files() -> List[Dict[str, str]]:
    """
    Helper to run layout validation directly using files on disk.
    If PBIP has not been compiled, it creates transient mock layouts
    and model schemas based on upstream json configurations.
    """
    from modules.pbip_generator import get_project_slug
    from modules.file_manager import OUTPUT_DIR
    import json

    project_slug = get_project_slug()
    report_json_path = OUTPUT_DIR / "pbip" / f"{project_slug}.Report" / "report.json"
    model_bim_path = OUTPUT_DIR / "pbip" / f"{project_slug}.SemanticModel" / "model.bim"
    report_def_path = OUTPUT_DIR / "report_definition.json"

    if not report_def_path.exists():
        return [{
            "visual": "System",
            "status": "Error",
            "issue": "report_definition.json is missing.",
            "recommendation": "Generate report definition first."
        }]
    
    with open(report_def_path, "r", encoding="utf-8") as f:
        report_def = json.load(f)

    if not model_bim_path.exists():
        # Fall back to analytics_model.json
        analytics_model_path = OUTPUT_DIR / "analytics_model.json"
        if not analytics_model_path.exists():
            return [{
                "visual": "System",
                "status": "Error",
                "issue": "Semantic model (model.bim or analytics_model.json) is missing.",
                "recommendation": "Generate analytics model first."
            }]
        
        with open(analytics_model_path, "r", encoding="utf-8") as f:
            analytics_model = json.load(f)
            
        # Mock a minimal model.bim structure for validation
        model_data = {"model": {"tables": []}}
        for t in analytics_model.get("fact_tables", []) + analytics_model.get("dimension_tables", []):
            model_data["model"]["tables"].append({
                "name": t["name"],
                "columns": [{"name": c["name"]} for c in t.get("columns", [])],
                "measures": []
            })
            
        # Add measures from dax_artifacts.json or report_definition.json
        dax_path = OUTPUT_DIR / "dax_artifacts.json"
        measures_list = []
        if dax_path.exists():
            with open(dax_path, "r", encoding="utf-8") as f:
                dax_list = json.load(f)
                measures_list = [{"name": m["measure_name"]} for m in dax_list]
        else:
            measures_list = [{"name": m["name"]} for m in report_def.get("measures", [])]
        
        # Add measures table
        model_data["model"]["tables"].append({
            "name": "_Measures",
            "columns": [],
            "measures": measures_list
        })
    else:
        with open(model_bim_path, "r", encoding="utf-8") as f:
            model_data = json.load(f)

    if not report_json_path.exists():
        # Mock report_data from report_def for validation before compilation
        report_data = {"sections": []}
        for p in report_def.get("pages", []):
            vc = []
            for v in p.get("visuals", []):
                # mock visual config
                vc.append({
                    "config": json.dumps({
                        "name": v.get("title", ""),
                        "singleVisual": {
                            "visualType": v.get("visual_type", "table"),
                            "vcObjects": {
                                "title": [{"properties": {"text": {"expr": {"Literal": {"Value": f"'{v.get('title', '')}'"}}}}}]
                            }
                        }
                    })
                })
            report_data["sections"].append({
                "displayName": p["page_name"],
                "visualContainers": vc
            })
    else:
        with open(report_json_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)

    return validate_report_layout(report_data, model_data, report_def)

