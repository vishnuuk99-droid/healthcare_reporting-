"""
Report Intelligence Engine Module.

Analyzes CMS requirements and analytics models, determines dashboard pages,
allocates conformed grid layout coordinates, generates/injects conformed DAX measures,
and compiles visual definitions using the Report Visual Compiler.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

from modules.file_manager import OUTPUT_DIR
from modules.report_visual_compiler import compile_visual_config

_REQUIREMENTS_FILE = OUTPUT_DIR / "requirements.json"
_REPORT_DEFINITION_FILE = OUTPUT_DIR / "report_definition.json"
_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"
_MEASURES_FILE = OUTPUT_DIR / "measures.json"
_DAX_ARTIFACTS_FILE = OUTPUT_DIR / "dax_artifacts.json"

_REPORT_LAYOUT_FILE = OUTPUT_DIR / "report_layout.json"
_REPORT_VISUALS_FILE = OUTPUT_DIR / "report_visuals.json"


def determine_optimal_visual_type(dimensions: List[str], measures: List[str], title: str = "", page_name: str = "", raw_type: str = "") -> str:
    """
    Determine the optimal visual type based on dimensions, measures, and title attributes.
    """
    # Check if percentage KPI
    is_percentage = False
    for m in measures:
        m_lower = m.lower()
        if "%" in m_lower or "rate" in m_lower or "ratio" in m_lower or "percentage" in m_lower:
            is_percentage = True
            break
            
    # Check dimensions
    has_date_dim = False
    has_geo_dim = False
    for d in dimensions:
        d_lower = d.lower()
        if "date" in d_lower or "month" in d_lower or "year" in d_lower or "day" in d_lower:
            has_date_dim = True
        if "zip" in d_lower or "state" in d_lower or "city" in d_lower or "country" in d_lower or "location" in d_lower:
            has_geo_dim = True

    title_lower = title.lower()

    # 1. Geographic attributes -> Map
    if has_geo_dim:
        return "map"

    # 2. Single KPI measure -> Card / KPI Card
    if len(dimensions) == 0 and len(measures) == 1:
        if is_percentage:
            return "kpi"
        else:
            return "card"

    # 3. Measure by Date -> Line Chart
    if has_date_dim and len(measures) >= 1:
        return "line_chart"

    # 4. Cross-tab analysis -> Matrix
    if len(dimensions) >= 2 and len(measures) >= 1 and (raw_type.lower() in ("matrix", "pivot") or "matrix" in title_lower or "cross" in title_lower):
        return "matrix"

    # 5. Multi-metric comparison -> Column Chart
    if len(measures) > 1 and len(dimensions) == 1:
        return "column_chart"

    # 6. Part-to-Whole -> Pie / Donut Chart
    is_part_to_whole = False
    for d in dimensions:
        d_lower = d.lower()
        if "disposition" in d_lower or "status" in d_lower or "priority" in d_lower or "gender" in d_lower or "type" in d_lower:
            is_part_to_whole = True
    if is_part_to_whole and len(dimensions) == 1 and len(measures) == 1:
        return "donut_chart"

    # 7. Detailed records / Listing -> Table
    if len(dimensions) >= 2 or raw_type.lower() in ("table", "list", "detail") or "detail" in title_lower or "list" in title_lower or "table" in title_lower:
        return "table"

    # 8. Measure by Category -> Clustered Bar Chart
    if len(dimensions) == 1 and len(measures) == 1:
        return "clustered_bar_chart"

    # Fallback to the raw type if provided
    if raw_type:
        rt = raw_type.lower()
        if rt in ("card", "kpi", "line_chart", "clustered_bar_chart", "pie_chart", "donut_chart", "table", "matrix", "column_chart", "map"):
            return rt

    return "table"


def allocate_coordinates(visuals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Allocates layout coordinates dynamically based on visual type.
    """
    cards = []
    charts = []
    tables = []
    
    for v in visuals:
        v_type = v["visual_type"].lower()
        if v_type in ("card", "kpi", "gauge"):
            cards.append(v)
        elif v_type in ("table", "matrix"):
            tables.append(v)
        else:
            charts.append(v)
            
    positioned_visuals = []
    
    # Position cards at the top row (y = 20)
    for idx, c in enumerate(cards):
        row_idx = idx // 4
        col_idx = idx % 4
        c["position"] = {
            "x": 20 + col_idx * 300,
            "y": 20 + row_idx * 170,
            "width": 280,
            "height": 150
        }
        positioned_visuals.append(c)
        
    # Determine starting y-coordinate for charts
    start_chart_y = 190
    if cards:
        num_card_rows = (len(cards) + 3) // 4
        start_chart_y = 20 + num_card_rows * 170
        
    # Position charts in rows of 2
    for idx, ch in enumerate(charts):
        row_idx = idx // 2
        col_idx = idx % 2
        ch["position"] = {
            "x": 20 + col_idx * 580,
            "y": start_chart_y + row_idx * 340,
            "width": 560,
            "height": 320
        }
        positioned_visuals.append(ch)
        
    # Determine starting y-coordinate for tables/matrices
    start_table_y = start_chart_y
    if charts:
        num_chart_rows = (len(charts) + 1) // 2
        start_table_y = start_chart_y + num_chart_rows * 340
        
    # Position tables/matrices (full-width)
    for idx, tb in enumerate(tables):
        tb["position"] = {
            "x": 20,
            "y": start_table_y + idx * 320,
            "width": 1200,
            "height": 300
        }
        positioned_visuals.append(tb)
        
    return positioned_visuals


def run_report_intelligence_engine() -> Dict[str, Any]:
    """
    Executes the intelligence engine to analyze models, register required measures,
    allocate coordinates, and write the layout and visual configurations.
    """
    # 1. Load inputs
    analytics_model = {}
    if _ANALYTICS_MODEL_FILE.exists():
        with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
            analytics_model = json.load(f)
            
    dax_list = []
    if _DAX_ARTIFACTS_FILE.exists():
        with open(_DAX_ARTIFACTS_FILE, "r", encoding="utf-8") as f:
            dax_list = json.load(f)
            
    measures_list = []
    if _MEASURES_FILE.exists():
        with open(_MEASURES_FILE, "r", encoding="utf-8") as f:
            measures_list = json.load(f)

    # 2. Inject conformed measures from structured metric definitions
    structured_metrics = []
    if _REQUIREMENTS_FILE.exists():
        with open(_REQUIREMENTS_FILE, "r", encoding="utf-8") as f:
            req_data = json.load(f)
            structured_metrics = req_data.get("structured_metrics", [])

    # Build required measures dynamically from structured definitions
    required_measures = []
    for sm in structured_metrics:
        metric_name = sm.get("metric_name", "")
        metric_type = sm.get("metric_type", "Count")
        if not metric_name:
            continue

        # Determine format string
        fmt = "#,##0"
        if metric_type in ("Percentage", "Ratio"):
            fmt = "0.0%"
        elif metric_type == "Average":
            fmt = "#,##0.0"

        # Determine classification
        classification = "Base Measure"
        if metric_type in ("Percentage", "Ratio"):
            classification = "Derived Measure"

        import re
        measure_id = re.sub(r"[^\w\s]", "", metric_name).strip().lower()
        measure_id = re.sub(r"[\s]+", "_", measure_id)

        required_measures.append({
            "measure_id": measure_id,
            "display_name": metric_name,
            "business_definition": sm.get("business_definition", metric_name),
            "dax_expression": "",  # Will be filled by DAX generator
            "measure_type": metric_type,
            "classification": classification,
            "formula_description": sm.get("numerator", metric_name),
            "source_tables": [],
            "source_fields": [],
            "format_string": fmt,
        })
        
    # Fallback if no structured metrics
    if not required_measures:
        required_measures = []

    modified_dax = False
    existing_dax_ids = {m.get("measure_id") for m in dax_list}
    for rm in required_measures:
        if rm["measure_id"] not in existing_dax_ids:
            dax_list.append({
                "measure_id": rm["measure_id"],
                "display_name": rm["display_name"],
                "business_definition": rm["business_definition"],
                "dax_expression": rm["dax_expression"],
                "dependencies": []
            })
            modified_dax = True

    modified_measures = False
    existing_measure_ids = {m.get("measure_id") for m in measures_list}
    for rm in required_measures:
        if rm["measure_id"] not in existing_measure_ids:
            measures_list.append({
                "measure_id": rm["measure_id"],
                "display_name": rm["display_name"],
                "measure_type": rm["measure_type"],
                "classification": rm["classification"],
                "business_definition": rm["business_definition"],
                "formula_description": rm["formula_description"],
                "source_tables": rm["source_tables"],
                "source_fields": rm["source_fields"],
                "dependencies": [],
                "report_pages": ["Executive Summary", "Data Quality"],
                "visuals_used_in": []
            })
            modified_measures = True

    if modified_dax:
        with open(_DAX_ARTIFACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(dax_list, f, indent=2)
            
    if modified_measures:
        with open(_MEASURES_FILE, "w", encoding="utf-8") as f:
            json.dump(measures_list, f, indent=2)

    # 3. Analyze report_definition.json and determine conformed dashboard page structure
    report_def_data = {}
    if _REPORT_DEFINITION_FILE.exists():
        with open(_REPORT_DEFINITION_FILE, "r", encoding="utf-8") as f:
            try:
                report_def_data = json.load(f)
            except Exception:
                pass

    pages_list_from_def = report_def_data.get("pages", [])
    if not pages_list_from_def:
        # Fallback default pages if report_definition.json is empty/missing
        pages_list_from_def = [
            {
                "page_name": "Executive Summary",
                "purpose": "High-level overview of determination volumes, appeals, and timeliness KPIs.",
                "visuals": [
                    {
                        "title": "Total Organization Determinations",
                        "visual_type": "card",
                        "dimensions": [],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    },
                    {
                        "title": "Adverse Decision Rate",
                        "visual_type": "kpi",
                        "dimensions": [],
                        "measures": [{"measure_id": "adverse_decision_rate", "display_name": "Adverse Decision Rate"}]
                    },
                    {
                        "title": "Average Turnaround Time",
                        "visual_type": "card",
                        "dimensions": [],
                        "measures": [{"measure_id": "average_turnaround_time", "display_name": "Average Turnaround Time"}]
                    },
                    {
                        "title": "Clean Claim Rate",
                        "visual_type": "kpi",
                        "dimensions": [],
                        "measures": [{"measure_id": "clean_claim_rate", "display_name": "Clean Claim Rate"}]
                    },
                    {
                        "title": "Monthly Determination Volume Trend",
                        "visual_type": "line_chart",
                        "dimensions": ["DimDate.month_name"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    },
                    {
                        "title": "Outcome Distribution",
                        "visual_type": "donut_chart",
                        "dimensions": ["FactOrganizationDetermination.disposition"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    }
                ]
            },
            {
                "page_name": "Determinations Analysis",
                "purpose": "Detailed breakdown of organization determinations by priority, type, and disposition.",
                "visuals": [
                    {
                        "title": "Determinations by Provider",
                        "visual_type": "clustered_bar_chart",
                        "dimensions": ["DimProvider.provider_name"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    },
                    {
                        "title": "Determinations by Organization",
                        "visual_type": "clustered_bar_chart",
                        "dimensions": ["DimOrganization.organization_name"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    },
                    {
                        "title": "Decisions by Disposition",
                        "visual_type": "clustered_bar_chart",
                        "dimensions": ["FactOrganizationDetermination.disposition"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    },
                    {
                        "title": "Trend Analysis",
                        "visual_type": "line_chart",
                        "dimensions": ["DimDate.month_name"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    }
                ]
            },
            {
                "page_name": "Data Quality",
                "purpose": "CMS Data Quality, missingness rate, and validation error counts.",
                "visuals": [
                    {
                        "title": "Missing Data %",
                        "visual_type": "kpi",
                        "dimensions": [],
                        "measures": [{"measure_id": "missing_data_percent", "display_name": "Missing Data %"}]
                    },
                    {
                        "title": "Validation Errors",
                        "visual_type": "card",
                        "dimensions": [],
                        "measures": [{"measure_id": "validation_errors", "display_name": "Validation Errors"}]
                    },
                    {
                        "title": "Data Quality Score",
                        "visual_type": "kpi",
                        "dimensions": [],
                        "measures": [{"measure_id": "data_quality_score", "display_name": "Data Quality Score"}]
                    },
                    {
                        "title": "Quality Trend",
                        "visual_type": "line_chart",
                        "dimensions": ["DimDate.month_name"],
                        "measures": [{"measure_id": "quality_trend", "display_name": "Quality Trend"}]
                    }
                ]
            },
            {
                "page_name": "CMS Submission Dataset",
                "purpose": "Consolidated grid listing determinations, patients, and dispositions for CMS submission.",
                "visuals": [
                    {
                        "title": "CMS Submission Matrix",
                        "visual_type": "matrix",
                        "dimensions": ["FactOrganizationDetermination.disposition", "FactOrganizationDetermination.processing_priority"],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    },
                    {
                        "title": "CMS Submission Detail Table",
                        "visual_type": "table",
                        "dimensions": [
                            "FactOrganizationDetermination.od_number",
                            "DimPatient.mbi",
                            "FactOrganizationDetermination.processing_priority",
                            "FactOrganizationDetermination.disposition",
                            "FactOrganizationDetermination.decision_rationale"
                        ],
                        "measures": [{"measure_id": "total_org_determinations_override", "display_name": "Total Org Determinations Override"}]
                    }
                ]
            }
        ]

    # Load reporting intent for visual type enrichment
    intent_map = {}
    _INTENT_FILE_PATH = OUTPUT_DIR / "reporting_intent.json"
    if _INTENT_FILE_PATH.exists():
        with open(_INTENT_FILE_PATH, "r", encoding="utf-8") as f:
            try:
                intent_data = json.load(f)
                intents = intent_data.get("intents", []) if isinstance(intent_data, dict) else intent_data
                for item in intents:
                    req = item.get("requirement", "")
                    intent = item.get("intent", "")
                    rec_visual = item.get("recommended_visual", "")
                    if req:
                        intent_map[req] = {"intent": intent, "visual": rec_visual}
            except Exception:
                pass

    pages_spec = []
    for p in pages_list_from_def:
        page_name = p.get("page_name", "")
        purpose = p.get("purpose", "")
        visuals_in_page = p.get("visuals", [])
        
        # 1. Analyze and classify each visual to determine optimal visual type
        classified_visuals = []
        for v in visuals_in_page:
            v_title = v.get("title", "")
            raw_type = v.get("visual_type", "")
            dims = v.get("dimensions", [])
            meas = v.get("measures", [])
            
            # Enrich visual type from reporting intent
            intent_info = intent_map.get(v_title, {})
            if intent_info and intent_info.get("visual"):
                raw_type = intent_info["visual"]

            optimal_type = determine_optimal_visual_type(
                dimensions=dims,
                measures=meas,
                title=v_title,
                page_name=page_name,
                raw_type=raw_type
            )
            
            classified_visuals.append({
                "title": v_title,
                "visual_type": optimal_type,
                "dimensions": dims,
                "measures": meas,
                "business_reason": v.get("business_reason", v_title)
            })
            
        # 2. Allocate layout coordinates dynamically
        positioned_visuals = allocate_coordinates(classified_visuals)
        
        pages_spec.append({
            "page_name": page_name,
            "purpose": purpose,
            "visuals": positioned_visuals
        })

    report_layout = {
        "report_name": report_def_data.get("report_name", "CMS Organization Determinations, Appeals, and Grievances Report"),
        "canvas_size": {"width": 1280, "height": 720},
        "pages": pages_spec
    }

    # 4. Save report_layout.json
    with open(_REPORT_LAYOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report_layout, f, indent=2)

    # 5. Compile all visuals and map to report_visuals.json
    compiled_visuals = {}
    
    for p in pages_spec:
        page_name = p["page_name"]
        for v in p["visuals"]:
            v_title = v["title"]
            v_type = v["visual_type"]
            dims = v["dimensions"]
            meas = v["measures"]
            pos = v["position"]
            
            # Generate a conformed GUID
            v_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{page_name}_{v_title}"))
            
            # Compile using visual compiler
            compiled = compile_visual_config(
                visual_id=v_id,
                title=v_title,
                visual_type=v_type,
                dimensions=dims,
                measures=meas,
                position=pos
            )
            compiled_visuals[v_id] = compiled

    # Save report_visuals.json
    with open(_REPORT_VISUALS_FILE, "w", encoding="utf-8") as f:
        json.dump(compiled_visuals, f, indent=2)

    # 6. Synchronize and update report_definition.json
    report_definition_sync = {
        "report_name": report_layout["report_name"],
        "pages": [
            {
                "page_name": p["page_name"],
                "purpose": p["purpose"],
                "visuals": [
                    {
                        "title": v["title"],
                        "visual_type": v["visual_type"],
                        "dimensions": v["dimensions"],
                        "measures": v["measures"],
                        "business_reason": v["title"]
                    }
                    for v in p["visuals"]
                ]
            }
            for p in pages_spec
        ],
        "filters": report_def_data.get("filters", [
            {
                "name": "Reporting Year",
                "field": "DimDate.year",
                "filter_type": "dropdown",
                "default_value": "2026",
                "scope": "report"
            }
        ]),
        "measures": [
            {
                "measure_id": rm["measure_id"],
                "display_name": rm["display_name"],
                "dax_expression": rm["dax_expression"],
                "format_string": "0.0%" if rm["measure_type"] == "Percentage" else "#,##0",
                "description": rm["business_definition"],
                "home_table": rm["source_tables"][0] if rm["source_tables"] else "_Measures"
            }
            for rm in required_measures
        ]
    }
    
    with open(_REPORT_DEFINITION_FILE, "w", encoding="utf-8") as f:
        json.dump(report_definition_sync, f, indent=2)

    return {
        "status": "Success",
        "report_layout_path": str(_REPORT_LAYOUT_FILE.resolve()),
        "report_visuals_path": str(_REPORT_VISUALS_FILE.resolve()),
        "pages_generated": len(pages_spec),
        "visuals_compiled": len(compiled_visuals),
        "measures_injected": len(required_measures)
    }


if __name__ == "__main__":
    res = run_report_intelligence_engine()
    print(json.dumps(res, indent=2))

