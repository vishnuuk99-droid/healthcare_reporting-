"""
Report Visual Compiler Module.

Converts visual definitions in report_definition.json into fully bound Power BI
visual config structures with valid projections, queryRefs, and prototypeQuery.
"""

from typing import Any, Dict, List, Set, Tuple


_VISUAL_TYPE_MAP = {
    "Card": "card",
    "Table": "tableEx",
    "Matrix": "pivotTable",
    "Line Chart": "lineChart",
    "Bar Chart": "clusteredBarChart",
}


def compile_visual_config(
    visual_id: str,
    title: str,
    visual_type: str,
    dimensions: List[str],
    measures: List[str],
    position: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compile a report visual spec into a fully bound Power BI visualContainer config.

    Args:
        visual_id: Unique GUID or name string for the visual container.
        title: Visual title to display.
        visual_type: Visual type (e.g. Card, Table, Matrix, Line Chart, Bar Chart).
        dimensions: List of dimension column strings (e.g. DimDate.month_name).
        measures: List of measure name strings (e.g. Total Org Determinations Override).
        position: Dictionary containing layout coordinates (x, y, width, height, z).

    Returns:
        A dict representing the fully compiled visual container config.
    """
    # 1. Map to official Power BI visual type string
    pbi_type = _VISUAL_TYPE_MAP.get(visual_type, "tableEx")
    
    # 2. Extract and format query references
    # All dimensions/measures should be referenced in projections as Table.Name
    query_fields = []
    
    for d in dimensions:
        if "." in d:
            tbl, col = d.split(".", 1)
        else:
            tbl = "DimPatient" # fallback table prefix
            col = d
        query_fields.append({
            "queryRef": f"{tbl}.{col}",
            "table": tbl,
            "property": col,
            "is_measure": False
        })
        
    for m in measures:
        m_clean = m.split(".", 1)[1] if "." in m else m
        tbl = "_Measures"
        query_fields.append({
            "queryRef": f"{tbl}.{m_clean}",
            "table": tbl,
            "property": m_clean,
            "is_measure": True
        })

    # 3. Build projections depending on visual type
    projections = {}
    if pbi_type in ["card", "gauge"]:
        # Card/Gauge takes exactly 1 measure in Values
        meas_fields = [f for f in query_fields if f["is_measure"]]
        projections["Values"] = [{"queryRef": f["queryRef"]} for f in meas_fields[:1]]
    elif pbi_type == "lineChart" or pbi_type == "clusteredBarChart":
        # Line/Bar chart: Category = first dimension, Y = measures list
        dim_fields = [f for f in query_fields if not f["is_measure"]]
        meas_fields = [f for f in query_fields if f["is_measure"]]
        projections["Category"] = [{"queryRef": f["queryRef"]} for f in dim_fields[:1]]
        projections["Y"] = [{"queryRef": f["queryRef"]} for f in meas_fields]
    elif pbi_type == "pivotTable":
        # Matrix: Rows = first dimension, Columns = second dimension (if any), Values = measures
        dim_fields = [f for f in query_fields if not f["is_measure"]]
        meas_fields = [f for f in query_fields if f["is_measure"]]
        projections["Rows"] = [{"queryRef": f["queryRef"]} for f in dim_fields[:1]]
        if len(dim_fields) > 1:
            projections["Columns"] = [{"queryRef": f["queryRef"]} for f in dim_fields[1:2]]
        projections["Values"] = [{"queryRef": f["queryRef"]} for f in meas_fields]
    else: # tableEx
        # Table: Values = all dimensions and measures
        projections["Values"] = [{"queryRef": f["queryRef"]} for f in query_fields]

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

    # 5. Assemble final Visual Container structure
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
