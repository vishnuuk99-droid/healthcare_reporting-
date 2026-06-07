"""
Test script for verifying report_visual_compiler.py and its integration with report_layout_validator.py.
"""

import sys
import json
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from modules.report_visual_compiler import compile_visual_config
from modules.report_layout_validator import validate_report_layout

def test_visual_compiler():
    print("Running Report Visual Compiler tests...\n")

    # Define simple mock variables
    visual_id = "test_visual_01"
    title = "Monthly Admission Trends"
    visual_type = "Line Chart"
    dimensions = ["DimDate.month_name"]
    measures = ["Total Org Determinations Override"]
    position = {"x": 10, "y": 20, "width": 400, "height": 300, "z": 0}

    # 1. Compile a visual config
    compiled = compile_visual_config(
        visual_id=visual_id,
        title=title,
        visual_type=visual_type,
        dimensions=dimensions,
        measures=measures,
        position=position
    )

    # 2. Inspect structure
    print("Compiled visual structure:")
    print(json.dumps(compiled, indent=2))

    # Assertions on compiled output structure
    assert compiled["name"] == visual_id
    assert compiled["layouts"][0]["position"]["x"] == 10
    assert compiled["layouts"][0]["position"]["y"] == 20
    assert compiled["layouts"][0]["position"]["width"] == 400
    assert compiled["layouts"][0]["position"]["height"] == 300

    single_visual = compiled["singleVisual"]
    assert single_visual["visualType"] == "lineChart"
    
    # Check projections
    projections = single_visual["projections"]
    assert "Category" in projections
    assert len(projections["Category"]) == 1
    assert projections["Category"][0]["queryRef"] == "DimDate.month_name"
    
    assert "Y" in projections
    assert len(projections["Y"]) == 1
    assert projections["Y"][0]["queryRef"] == "_Measures.Total Org Determinations Override"

    # Check prototypeQuery
    pq = single_visual["prototypeQuery"]
    assert pq["Version"] == 2
    
    from_list = pq["From"]
    # We should have references to DimDate and _Measures
    entities = {f["Entity"] for f in from_list}
    assert "DimDate" in entities
    assert "_Measures" in entities
    
    select_list = pq["Select"]
    assert len(select_list) == 2
    
    # Check name and column/measure mappings
    names = {s["Name"] for s in select_list}
    assert "DimDate.month_name" in names
    assert "_Measures.Total Org Determinations Override" in names

    # 3. Test integration with validate_report_layout
    # Mock model
    mock_model = {
        "model": {
            "tables": [
                {
                    "name": "DimDate",
                    "columns": [{"name": "month_name"}],
                    "measures": []
                },
                {
                    "name": "_Measures",
                    "columns": [],
                    "measures": [{"name": "Total Org Determinations Override"}]
                }
            ]
        }
    }

    # Mock report layout containing the compiled visual
    mock_report_layout = {
        "sections": [
            {
                "displayName": "Trends Page",
                "visualContainers": [
                    {
                        "config": json.dumps(compiled)
                    }
                ]
            }
        ]
    }

    # Mock report definition
    mock_report_def = {
        "report_name": "Test Report",
        "pages": [
            {
                "page_name": "Trends Page",
                "visuals": [
                    {
                        "title": title,
                        "visual_type": "line_chart",
                        "dimensions": dimensions,
                        "measures": measures
                    }
                ]
            }
        ]
    }

    # Validate
    issues = validate_report_layout(mock_report_layout, mock_model, mock_report_def)
    print(f"\nLayout Validation Issues for Compiled Visual: {len(issues)}")
    for issue in issues:
        print(f"- Visual: {issue['visual']} | {issue['status']}: {issue['issue']}")

    # There should be no issues because everything was compiled properly!
    assert len(issues) == 0, f"Expected 0 issues for fully compiled visual, but got: {issues}"
    print("Integration validation check passed!")


def test_invalid_visual_rejection():
    # 4. Test that empty/uncompiled visuals are rejected by the validator
    mock_model = {
        "model": {
            "tables": [
                {
                    "name": "DimDate",
                    "columns": [{"name": "month_name"}],
                    "measures": []
                },
                {
                    "name": "_Measures",
                    "columns": [],
                    "measures": [{"name": "Total Org Determinations Override"}]
                }
            ]
        }
    }

    # Visual with empty projections/prototypeQuery (textbox/image excluded)
    empty_visual_config = {
        "name": "empty_v",
        "singleVisual": {
            "visualType": "lineChart",
            "projections": {},
            "prototypeQuery": {}
        }
    }

    mock_report_layout = {
        "sections": [
            {
                "displayName": "Trends Page",
                "visualContainers": [
                    {
                        "config": json.dumps(empty_visual_config)
                    }
                ]
            }
        ]
    }

    mock_report_def = {
        "report_name": "Test Report",
        "pages": [
            {
                "page_name": "Trends Page",
                "visuals": [
                    {
                        "title": "empty_v",
                        "visual_type": "line_chart",
                        "dimensions": ["DimDate.month_name"],
                        "measures": ["Total Org Determinations Override"]
                    }
                ]
            }
        ]
    }

    issues = validate_report_layout(mock_report_layout, mock_model, mock_report_def)
    print(f"\nLayout Validation Issues for Empty/Uncompiled Visual: {len(issues)}")
    for issue in issues:
        print(f"- Visual: {issue['visual']} | {issue['status']}: {issue['issue']}")

    # We expect empty projections and empty prototypeQuery to be flagged
    assert len(issues) >= 2, "Expected empty projections and empty prototypeQuery errors"
    assert any("empty projections" in i["issue"] for i in issues)
    assert any("empty prototypeQuery" in i["issue"] for i in issues)
    print("Invalid visual rejection check passed!")


if __name__ == "__main__":
    test_visual_compiler()
    test_invalid_visual_rejection()
    print("\nAll Report Visual Compiler tests completed successfully!")
