"""
Report Layout Validator Module.

Validates report.json against the semantic model (model.bim) before PBIP packaging.
Performs 8 checks to ensure layout, visual configurations, and bindings are valid.
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
        A list of validation issues found.
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
        
        for m in t.get("measures", []):
            measures_set.add(m.get("name", ""))

    # ── 2. Run Checks ──────────────────────────────────────────────────
    report_visual_titles = set()
    report_visual_by_title = {}
    seen_visual_ids = set()

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
                
                # Check: Duplicate Visual IDs
                if v_name:
                    if v_name in seen_visual_ids:
                        issues.append({
                            "visual": v_title,
                            "status": "Error",
                            "issue": f"Duplicate visual ID '{v_name}' detected in layout.",
                            "recommendation": "Ensure visual container IDs generated are unique."
                        })
                    seen_visual_ids.add(v_name)

                # Check: Invalid Visual Type
                valid_pbi_types = {"card", "kpi", "gauge", "lineChart", "clusteredBarChart", "pieChart", "donutChart", "tableEx", "pivotTable", "clusteredColumnChart", "map", "textbox", "image", "slicer", "cardVisual", "barChart", "columnChart", "azureMap"}
                if v_type and v_type not in valid_pbi_types:
                    issues.append({
                        "visual": v_title,
                        "status": "Error",
                        "issue": f"Invalid Power BI visual type '{v_type}' detected.",
                        "recommendation": f"Use one of conformed types: {list(valid_pbi_types)}"
                    })


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
                        
                    # Reject tableEx for KPI or chart requirements
                    is_kpi_or_chart_req = False
                    spec_v_type = None
                    for p_spec in report_def.get("pages", []):
                        for v_spec in p_spec.get("visuals", []):
                            if v_spec.get("title", "") == v_title:
                                spec_v_type = v_spec.get("visual_type", "").lower()
                                break
                        if spec_v_type:
                            break
                    
                    if spec_v_type and spec_v_type in ["card", "kpi", "line_chart", "clustered_bar_chart", "pie_chart", "donut_chart", "column_chart", "map"]:
                        is_kpi_or_chart_req = True
                        
                    if is_kpi_or_chart_req and v_type == "tableEx":
                        issues.append({
                            "visual": v_title,
                            "status": "Error",
                            "issue": f"Visual '{v_title}' has visualType 'tableEx' but the requirement '{spec_v_type}' expects a KPI or chart visual.",
                            "recommendation": "Update report visual compiler to assign correct visualType."
                        })

                    # Check required data roles
                    if v_type == "kpi":
                        required_roles = ["Indicator"]
                    elif v_type in ["card", "gauge", "tableEx"]:
                        required_roles = ["Values"]
                    elif v_type in ["lineChart", "clusteredBarChart", "donutChart", "pieChart", "clusteredColumnChart"]:
                        required_roles = ["Category", "Y"]
                    elif v_type == "pivotTable":
                        required_roles = ["Rows", "Values"]
                    elif v_type == "map":
                        required_roles = ["Category", "Size"]
                    else:
                        required_roles = []
                        
                    for role in required_roles:
                        if role not in projections or not projections[role]:
                            issues.append({
                                "visual": v_title,
                                "status": "Error",
                                "issue": f"Required data role '{role}' is missing from projections for visual type '{v_type}'.",
                                "recommendation": f"Add field bindings to satisfy '{role}' projection role."
                            })

                    # Check: Missing queryRef and bindings in projections
                    if projections:
                        for proj_name, proj_list in projections.items():
                            for proj_item in proj_list:
                                qref = proj_item.get("queryRef", "")
                                if not qref:
                                    issues.append({
                                        "visual": v_title,
                                        "status": "Error",
                                        "issue": f"Visual '{v_title}' has a projection item with missing queryRef.",
                                        "recommendation": "Recompile visual config to generate query references."
                                    })
                                else:
                                    # Ensure queryRef is bound in prototypeQuery select list
                                    select_items = prototype_query.get("Select", []) if isinstance(prototype_query, dict) else []
                                    select_names = {s.get("Name", "") for s in select_items}
                                    if qref not in select_names:
                                        issues.append({
                                            "visual": v_title,
                                            "status": "Error",
                                            "issue": f"QueryRef '{qref}' in projections is missing from prototypeQuery Select.",
                                            "recommendation": "Synchronize projections and prototypeQuery SELECT properties."
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

    # Check: Detect Orphan Visual References
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

        # Check: Bindings Validation (Fields, Tables, Measures)
        for d_field in dims:
            # Support both DimDate.Month and DimDate[Month] syntax
            if "[" in d_field and d_field.endswith("]"):
                tbl, col = d_field[:-1].split("[", 1)
            elif "." in d_field:
                tbl, col = d_field.split(".", 1)
            else:
                # Column referenced without table name
                found = False
                for tbl_name, cols in tables_dict.items():
                    if d_field in cols:
                        found = True
                        tbl, col = tbl_name, d_field
                        break
                if not found:
                    issues.append({
                        "visual": title,
                        "status": "Error",
                        "issue": f"Dimension field '{d_field}' does not exist in any table of model.bim.",
                        "recommendation": "Specify field with table prefix (e.g. Table.Field) and verify spelling."
                    })
                    continue

            # Check: Table exists
            if tbl not in tables_dict:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Table '{tbl}' referenced in dimension '{d_field}' does not exist in model.bim.",
                    "recommendation": f"Verify if '{tbl}' was renamed or omitted during star schema generation."
                })
            # Check: Field exists in table
            elif col not in tables_dict[tbl]:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Column '{col}' in table '{tbl}' does not exist in model.bim.",
                    "recommendation": f"Verify if column '{col}' is named correctly in table '{tbl}'."
                })

        for m_field in meas:
            # Support both _Measures[Total] and _Measures.Total and native Total
            if "[" in m_field and m_field.endswith("]"):
                m_clean = m_field[:-1].split("[", 1)[1]
            elif "." in m_field:
                m_clean = m_field.split(".", 1)[1]
            else:
                m_clean = m_field

            if m_clean not in measures_set:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Measure '{m_field}' does not exist in model.bim.",
                    "recommendation": f"Verify if the measure '{m_field}' was compiled in dax_artifacts.json."
                })

        # Check: Visual type required properties
        v_type_lower = v_type.lower()
        if v_type_lower in ["card", "gauge"]:
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
        elif v_type_lower in ["line_chart", "bar_chart", "donut_chart", "pie_chart", "column_chart", "clustered_bar_chart"]:
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
        elif v_type_lower == "matrix":
            if len(dims) < 1:
                issues.append({
                    "visual": title,
                    "status": "Error",
                    "issue": f"Matrix visual requires at least 1 dimension to define rows/columns.",
                    "recommendation": "Add row/column dimensions."
                })
        elif v_type_lower == "table":
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
        applied_fixes: List of fixes applied.
        validation_results: Dict containing layout validation results.
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
        available_measures.update(m.get("name", "") for m in report_def.get("measures", []))

    applied_fixes = []
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
                # Support both dot and bracket
                if "[" in d_field and d_field.endswith("]"):
                    tbl, col = d_field[:-1].split("[", 1)
                    is_bracket = True
                elif "." in d_field:
                    tbl, col = d_field.split(".", 1)
                    is_bracket = False
                else:
                    tbl, col = "", d_field
                    is_bracket = False

                if tbl:
                    if tbl not in valid_tables:
                        if col in model_columns_map:
                            new_tbl = model_columns_map[col][0]
                            corrected_dims.append(f"{new_tbl}[{col}]" if is_bracket else f"{new_tbl}.{col}")
                            table_replacements[tbl] = new_tbl
                            applied_fixes.append({
                                "visual": title,
                                "issue": f"Dimension references missing table '{tbl}' in field '{d_field}'.",
                                "fix_applied": f"Remapped field to '{new_tbl}.{col}' (found column in '{new_tbl}')."
                            })
                        else:
                            similar_tables = difflib.get_close_matches(tbl, list(valid_tables), n=1, cutoff=0.5)
                            if similar_tables:
                                new_tbl = similar_tables[0]
                                corrected_dims.append(f"{new_tbl}[{col}]" if is_bracket else f"{new_tbl}.{col}")
                                table_replacements[tbl] = new_tbl
                                applied_fixes.append({
                                    "visual": title,
                                    "issue": f"Dimension references missing table '{tbl}' in field '{d_field}'.",
                                    "fix_applied": f"Remapped table '{tbl}' to '{new_tbl}' (similar table name)."
                                })
                            else:
                                corrected_dims.append(d_field)
                    else:
                        corrected_dims.append(d_field)
                else:
                    if d_field not in model_columns_map:
                        similar_cols = difflib.get_close_matches(d_field, list(model_columns_map.keys()), n=1, cutoff=0.6)
                        if similar_cols:
                            new_col = similar_cols[0]
                            new_tbl = model_columns_map[new_col][0]
                            corrected_dims.append(f"{new_tbl}[{new_col}]" if is_bracket else f"{new_tbl}.{new_col}")
                            applied_fixes.append({
                                "visual": title,
                                "issue": f"Field '{d_field}' is missing from the model.",
                                "fix_applied": f"Remapped to '{new_tbl}.{new_col}' (closest matching column)."
                            })
                        else:
                            corrected_dims.append(d_field)
                    else:
                        new_tbl = model_columns_map[d_field][0]
                        corrected_dims.append(f"{new_tbl}[{d_field}]" if is_bracket else f"{new_tbl}.{d_field}")
                        applied_fixes.append({
                            "visual": title,
                            "issue": f"Field '{d_field}' is missing table prefix.",
                            "fix_applied": f"Added prefix: '{new_tbl}.{d_field}'."
                        })
            v["dimensions"] = corrected_dims

            # (b) Check measures list
            corrected_meas = []
            for m_field in v.get("measures", []):
                if "[" in m_field and m_field.endswith("]"):
                    m_clean = m_field[:-1].split("[", 1)[1]
                elif "." in m_field:
                    m_clean = m_field.split(".", 1)[1]
                else:
                    m_clean = m_field

                if m_clean not in available_measures:
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
            v_type_lower = v_type.lower()
            if v_type_lower in ["card", "gauge"]:
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
            elif v_type_lower in ["line_chart", "bar_chart", "donut_chart", "pie_chart", "column_chart", "clustered_bar_chart"]:
                if len(v.get("dimensions", [])) == 0:
                    default_dim = "DimDate.month_name"
                    if "DimDate" in valid_tables and "month_name" in model_columns_map.get("month_name", []):
                        v["dimensions"] = [default_dim]
                    else:
                        found_dim = None
                        for tbl in valid_tables:
                            if tbl.startswith("Dim") and tbl != "DimDate":
                                cols = list(model_columns_map.keys())
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
            if "[" in f_field and f_field.endswith("]"):
                tbl, col = f_field[:-1].split("[", 1)
                is_bracket = True
            elif "." in f_field:
                tbl, col = f_field.split(".", 1)
                is_bracket = False
            else:
                tbl, col = "", f_field
                is_bracket = False

            if tbl and tbl not in valid_tables:
                if col in model_columns_map:
                    new_tbl = model_columns_map[col][0]
                    filt["field"] = f"{new_tbl}[{col}]" if is_bracket else f"{new_tbl}.{col}"
                    applied_fixes.append({
                        "visual": f"Filter: {filt.get('name', 'Unnamed')}",
                        "issue": f"Filter references missing table '{tbl}'.",
                        "fix_applied": f"Remapped to '{new_tbl}.{col}'."
                    })

    # ── 4. Synchronize dax_artifacts.json if tables were remapped ─────
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

    if measures_path.exists() and table_replacements:
        try:
            with open(measures_path, "r", encoding="utf-8") as f:
                m_list = json.load(f)
            
            m_modified = False
            for m in m_list:
                expr = m.get("dax_expression", "")
                if expr:
                    for old_t, new_t in table_replacements.items():
                        if old_t in expr:
                            expr = expr.replace(old_t, new_t)
                            m["dax_expression"] = expr
                            m_modified = True
                
                formula_desc = m.get("formula_description", "")
                if formula_desc:
                    for old_t, new_t in table_replacements.items():
                        if old_t in formula_desc:
                            formula_desc = formula_desc.replace(old_t, new_t)
                            m["formula_description"] = formula_desc
                            m_modified = True
                            
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

    compile_result = compile_pbip_project()

    # Rerun validation
    new_issues = validate_report_layout_from_files()


    return applied_fixes, {
        "status": "Success" if not new_issues else "Warning",
        "issues": new_issues,
        "compile_result": compile_result
    }


def validate_report_layout_from_files() -> List[Dict[str, str]]:
    """
    Helper to run layout validation directly using files on disk.
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
            
        model_data = {"model": {"tables": []}}
        for t in analytics_model.get("fact_tables", []) + analytics_model.get("dimension_tables", []):
            model_data["model"]["tables"].append({
                "name": t["name"],
                "columns": [{"name": c["name"]} for c in t.get("columns", [])],
                "measures": []
            })
            
        dax_path = OUTPUT_DIR / "dax_artifacts.json"
        measures_list = []
        if dax_path.exists():
            with open(dax_path, "r", encoding="utf-8") as f:
                dax_list = json.load(f)
                measures_list = [{"name": m["measure_name"]} for m in dax_list]
        else:
            measures_list = [{"name": m["name"]} for m in report_def.get("measures", [])]
        
        model_data["model"]["tables"].append({
            "name": "_Measures",
            "columns": [],
            "measures": measures_list
        })
    else:
        with open(model_bim_path, "r", encoding="utf-8") as f:
            model_data = json.load(f)

    report_dir = OUTPUT_DIR / "pbip" / f"{project_slug}.Report"
    pages_json_path = report_dir / "definition" / "pages" / "pages.json"
    
    report_data = None
    if pages_json_path.exists():
        try:
            with open(pages_json_path, "r", encoding="utf-8") as f:
                pages_meta = json.load(f)
            
            sections = []
            for page_folder in pages_meta.get("pageOrder", []):
                page_path = report_dir / "definition" / "pages" / page_folder / "page.json"
                if not page_path.exists():
                    continue
                with open(page_path, "r", encoding="utf-8") as f:
                    page_meta = json.load(f)
                
                visuals_dir = report_dir / "definition" / "pages" / page_folder / "visuals"
                visual_containers = []
                if visuals_dir.exists():
                    for visual_folder in visuals_dir.iterdir():
                        if not visual_folder.is_dir():
                            continue
                        visual_path = visual_folder / "visual.json"
                        if not visual_path.exists():
                            continue
                        with open(visual_path, "r", encoding="utf-8") as f:
                            visual_meta = json.load(f)
                        
                        pos = visual_meta.get("position", {})
                        v_name = visual_meta.get("name", "")
                        v_data = visual_meta.get("visual", {})
                        pbir_type = v_data.get("visualType", "")
                        
                        type_map_rev = {
                            "cardVisual": "card",
                            "barChart": "clusteredBarChart",
                            "columnChart": "clusteredColumnChart",
                            "azureMap": "map",
                            "tableEx": "tableEx",
                            "pivotTable": "pivotTable",
                            "textbox": "textbox",
                            "slicer": "slicer",
                            "kpi": "kpi",
                            "gauge": "gauge",
                            "lineChart": "lineChart",
                            "pieChart": "pieChart",
                            "donutChart": "donutChart"
                        }
                        legacy_type = type_map_rev.get(pbir_type, pbir_type)
                        
                        legacy_single_visual = {
                            "visualType": legacy_type,
                            "projections": {},
                            "prototypeQuery": {"Select": []}
                        }
                        
                        query_state = v_data.get("query", {}).get("queryState", {})
                        role_map_rev = {
                            "Data": "Values"
                        }
                        for role, content in query_state.items():
                            leg_role = role_map_rev.get(role, role)
                            legacy_single_visual["projections"][leg_role] = []
                            for p in content.get("projections", []):
                                qref = p.get("queryRef", "")
                                if "." in qref and not "[" in qref:
                                    tbl, prop = qref.split(".", 1)
                                    qref_bracket = f"{tbl}[{prop}]"
                                else:
                                    qref_bracket = qref
                                    
                                legacy_single_visual["projections"][leg_role].append({
                                    "queryRef": qref_bracket
                                })
                                
                                field_data = p.get("field", {})
                                if "Column" in field_data:
                                    legacy_single_visual["prototypeQuery"]["Select"].append({
                                        "Name": qref_bracket,
                                        "Column": {
                                            "Expression": { "SourceRef": { "Source": "x" } },
                                            "Property": field_data["Column"].get("Property", "")
                                        }
                                    })
                                elif "Measure" in field_data:
                                    legacy_single_visual["prototypeQuery"]["Select"].append({
                                        "Name": qref_bracket,
                                        "Measure": {
                                            "Expression": { "SourceRef": { "Source": "x" } },
                                            "Property": field_data["Measure"].get("Property", "")
                                        }
                                    })
                                    
                        vc_objects = {}
                        title_objs = v_data.get("visualContainerObjects", {}).get("title", [])
                        if title_objs:
                            vc_objects["title"] = title_objs
                        legacy_single_visual["vcObjects"] = vc_objects
                        
                        visual_container = {
                            "x": pos.get("x", 20),
                            "y": pos.get("y", 20),
                            "width": pos.get("width", 280),
                            "height": pos.get("height", 150),
                            "z": pos.get("z", 0),
                            "config": json.dumps({
                                "name": v_name,
                                "singleVisual": legacy_single_visual
                            }, ensure_ascii=False)
                        }
                        visual_containers.append(visual_container)
                        
                sections.append({
                    "displayName": page_meta.get("displayName", ""),
                    "name": page_meta.get("name", ""),
                    "visualContainers": visual_containers
                })
            
            report_data = {
                "sections": sections
            }
        except Exception as e:
            report_data = None
            
    if report_data is None:
        if report_json_path.exists():
            with open(report_json_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
        else:
            report_data = {"sections": []}
            for p in report_def.get("pages", []):
                vc = []
                for v in p.get("visuals", []):
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

    return validate_report_layout(report_data, model_data, report_def)

