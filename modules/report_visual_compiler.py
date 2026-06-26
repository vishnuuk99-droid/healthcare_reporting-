"""
Report Visual Compiler Module.

Converts visual definitions into fully conformed Power BI visual config structures
with conformed bracket queryRefs (e.g. Table[Field]), projections, prototypeQuery,
dataRoles, sorting, and formatting.
"""

from typing import Any, Dict, List, Set, Tuple

_VISUAL_TYPE_MAP = {
    "card": "card",
    "kpi": "kpi",
    "gauge": "gauge",
    "line_chart": "lineChart",
    "clustered_bar_chart": "clusteredBarChart",
    "bar_chart": "clusteredBarChart",
    "pie_chart": "pieChart",
    "donut_chart": "donutChart",
    "table": "tableEx",
    "matrix": "pivotTable",
    "column_chart": "clusteredColumnChart",
    "map": "map",
}


def compile_visual_config(
    visual_id: str,
    title: str,
    visual_type: str,
    dimensions: List[str],
    measures: List[Any],
    position: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compile a report visual spec into a fully bound Power BI visualContainer config.

    Args:
        visual_id: Unique GUID or name string for the visual container.
        title: Visual title to display.
        visual_type: Visual type (e.g. card, kpi, table, matrix, line_chart, clustered_bar_chart, donut_chart).
        dimensions: List of dimension column strings (e.g. DimDate.month_name).
        measures: List of measure name strings (e.g. Total Org Determinations Override).
        position: Dictionary containing layout coordinates (x, y, width, height, z).

    Returns:
        A dict representing the fully compiled visual container config.
    """
    # 1. Map to official Power BI visual type string
    v_type_clean = visual_type.lower().replace(" ", "_").replace("-", "_")
    pbi_type = _VISUAL_TYPE_MAP.get(v_type_clean, "tableEx")
    
    # 2. Extract and format query references in conformed bracket format Entity[Property]
    query_fields = []
    
    for d in dimensions:
        if "[" in d and d.endswith("]"):
            tbl, col = d[:-1].split("[", 1)
        elif "." in d:
            tbl, col = d.split(".", 1)
        else:
            tbl = "DimPatient" # fallback table prefix
            col = d
        query_fields.append({
            "queryRef": f"{tbl}[{col}]",
            "table": tbl,
            "property": col,
            "is_measure": False
        })
        
    for m in measures:
        if isinstance(m, dict):
            m_name = m.get("display_name", m.get("measure_id", ""))
        else:
            m_name = m
            
        if "[" in m_name and m_name.endswith("]"):
            tbl, m_clean = m_name[:-1].split("[", 1)
        elif "." in m_name:
            tbl, m_clean = m_name.split(".", 1)
        else:
            tbl = "_Measures"
            m_clean = m_name
        query_fields.append({
            "queryRef": f"{tbl}[{m_clean}]",
            "table": tbl,
            "property": m_clean,
            "is_measure": True
        })

    # 3. Build projections and dataRoles depending on visual type
    projections = {}
    data_roles = []
    
    dim_fields = [f for f in query_fields if not f["is_measure"]]
    meas_fields = [f for f in query_fields if f["is_measure"]]
    
    if pbi_type in ["card", "gauge"]:
        # Card/Gauge takes exactly 1 measure in Values
        projections["Values"] = [{"queryRef": f["queryRef"]} for f in meas_fields[:1]]
    elif pbi_type == "kpi":
        # KPI Card: Indicator = first measure, TrendValues = first dimension
        projections["Indicator"] = [{"queryRef": f["queryRef"]} for f in meas_fields[:1]]
        if dim_fields:
            projections["TrendValues"] = [{"queryRef": dim_fields[0]["queryRef"]}]
    elif pbi_type in ["lineChart", "clusteredBarChart", "donutChart", "pieChart", "clusteredColumnChart"]:
        # Line/Bar/Column/Donut/Pie chart: Category = first dimension, Y = measures list
        projections["Category"] = [{"queryRef": f["queryRef"]} for f in dim_fields[:1]]
        projections["Y"] = [{"queryRef": f["queryRef"]} for f in meas_fields]
    elif pbi_type == "pivotTable":
        # Matrix: Rows = first dimension, Columns = second dimension (if any), Values = measures
        projections["Rows"] = [{"queryRef": f["queryRef"]} for f in dim_fields[:1]]
        if len(dim_fields) > 1:
            projections["Columns"] = [{"queryRef": f["queryRef"]} for f in dim_fields[1:2]]
        projections["Values"] = [{"queryRef": f["queryRef"]} for f in meas_fields]
    elif pbi_type == "map":
        # Map: Category = location dimension, Size = first measure
        projections["Category"] = [{"queryRef": f["queryRef"]} for f in dim_fields[:1]]
        if meas_fields:
            projections["Size"] = [{"queryRef": meas_fields[0]["queryRef"]}]
    else: # tableEx
        # Table: Values = all dimensions and measures
        projections["Values"] = [{"queryRef": f["queryRef"]} for f in query_fields]

    # Populate dataRoles matching projections
    for role, items in projections.items():
        for idx, item in enumerate(items):
            data_roles.append({
                "role": role,
                "projection": idx
            })

    # 4. Build prototypeQuery (Version 2 structure)
    # Gather unique tables referenced
    tables_referenced = sorted(list(set(f["table"] for f in query_fields)))
    
    # Assign unique aliases (e.g. DimDate -> d, _Measures -> m)
    alias_map = {}
    used_chars = set()
    for t in tables_referenced:
        first_char = t[0].lower() if t else 't'
        if first_char not in used_chars and first_char.isalpha():
            alias = first_char
        else:
            # find next available letter
            for c in "abcdefghijklmnopqrstuvwxyz":
                if c not in used_chars:
                    alias = c
                    break
            else:
                alias = "x"
        alias_map[t] = alias
        used_chars.add(alias)

    from_list = [{"Name": alias_map[t], "Entity": t} for t in tables_referenced]
    
    select_list = []
    for f in query_fields:
        alias = alias_map.get(f["table"], "x")
        if f["is_measure"]:
            select_item = {
                "Measure": {
                    "Expression": {
                        "SourceRef": {
                            "Source": alias
                        }
                    },
                    "Property": f["property"]
                },
                "Name": f["queryRef"]
            }
        else:
            select_item = {
                "Column": {
                    "Expression": {
                        "SourceRef": {
                            "Source": alias
                        }
                    },
                    "Property": f["property"]
                },
                "Name": f["queryRef"]
            }
        select_list.append(select_item)

    prototype_query = {
        "Version": 2,
        "From": from_list,
        "Select": select_list
    }

    # 5. Build sorting and formatting metadata
    sorting = {}
    if query_fields:
        sorting = {
            "implicit": {
                "sortDirection": 1,  # Ascending
                "sortBy": {
                    "queryRef": query_fields[0]["queryRef"]
                }
            }
        }

    formatting = {
        "show": True,
        "title": {
            "show": True,
            "text": title
        }
    }

    # 6. Assemble final Visual Container structure
    return {
        "name": visual_id,
        "layouts": [
            {
                "position": {
                    "x": position.get("x", 20),
                    "y": position.get("y", 20),
                    "width": position.get("width", 460),
                    "height": position.get("height", 300),
                    "z": position.get("z", 0)
                }
            }
        ],
        "singleVisual": {
            "visualType": pbi_type,
            "projections": projections,
            "prototypeQuery": prototype_query,
            "dataRoles": data_roles,
            "sorting": sorting,
            "formatting": formatting,
            "vcObjects": {
                "title": [
                    {
                        "properties": {
                            "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                            "show": {"expr": {"Literal": {"Value": "true"}}}
                        }
                    }
                ]
            }
        }
    }

