"""
Test script for verifying modules/report_layout_validator.py.
"""

import sys
import json
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from modules.report_layout_validator import validate_report_layout
from modules.pbip_generator import compile_pbip_project, validate_pbip_project


def test_validator():
    print("Running Report Layout Validator tests...\n")

    # 1. Define mock model.bim data
    mock_model = {
        "model": {
            "tables": [
                {
                    "name": "FactDetermination",
                    "columns": [
                        {"name": "determination_key"},
                        {"name": "patient_key"},
                        {"name": "disposition"},
                        {"name": "processing_priority"}
                    ],
                    "measures": []
                },
                {
                    "name": "DimDate",
                    "columns": [
                        {"name": "date_key"},
                        {"name": "month_name"}
                    ],
                    "measures": []
                },
                {
                    "name": "_Measures",
                    "columns": [],
                    "measures": [
                        {"name": "Total Org Determinations Override"},
                        {"name": "Adverse Decision Rate"}
                    ]
                }
            ]
        }
    }

    # 2. Define a malformed report spec containing multiple violations:
    # - Visual 1: Stale table reference "FactObservation.disposition" instead of "FactDetermination.disposition"
    # - Visual 2: Stale measure reference "Total Organization Determinations" instead of "Total Org Determinations Override"
    # - Visual 3: Visual type constraint violation (card with 2 measures and 1 dimension)
    # - Visual 4: Chart visual constraint violation (line chart with 0 dimensions)
    mock_report_def = {
        "report_name": "Test Report",
        "pages": [
            {
                "page_name": "Overview Page",
                "visuals": [
                    {
                        "title": "Decisions by Disposition",
                        "visual_type": "bar_chart",
                        "dimensions": [
                            "FactObservation.disposition" # Stale table reference
                        ],
                        "measures": [
                            "Total Org Determinations Override"
                        ]
                    },
                    {
                        "title": "Total Organization Determinations",
                        "visual_type": "card",
                        "dimensions": [],
                        "measures": [
                            "Total Organization Determinations" # Stale measure name
                        ]
                    },
                    {
                        "title": "Bad Card Properties",
                        "visual_type": "card",
                        "dimensions": ["DimDate.month_name"], # Cards should not have dimensions
                        "measures": ["Total Org Determinations Override", "Adverse Decision Rate"] # Cards should only have 1 measure
                    },
                    {
                        "title": "Bad Chart Properties",
                        "visual_type": "line_chart",
                        "dimensions": [], # Charts must have dimensions
                        "measures": ["Total Org Determinations Override"]
                    }
                ]
            }
        ]
    }

    # 3. Define a mock report.json layout representing visualContainers in report layout
    mock_report_layout = {
        "sections": [
            {
                "displayName": "Overview Page",
                "visualContainers": [
                    {
                        "config": json.dumps({
                            "name": "v1",
                            "singleVisual": {
                                "visualType": "clusteredBarChart",
                                "vcObjects": {
                                    "title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Decisions by Disposition'"}}}}}]
                                }
                            }
                        })
                    },
                    {
                        "config": json.dumps({
                            "name": "v2",
                            "singleVisual": {
                                "visualType": "card",
                                "vcObjects": {
                                    "title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Total Organization Determinations'"}}}}}]
                                }
                            }
                        })
                    },
                    {
                        "config": json.dumps({
                            "name": "v3",
                            "singleVisual": {
                                "visualType": "card",
                                "vcObjects": {
                                    "title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Bad Card Properties'"}}}}}]
                                }
                            }
                        })
                    },
                    {
                        "config": json.dumps({
                            "name": "v4",
                            "singleVisual": {
                                "visualType": "lineChart",
                                "vcObjects": {
                                    "title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Bad Chart Properties'"}}}}}]
                                }
                            }
                        })
                    }
                ]
            }
        ]
    }

    print("Auditing malformed layout...")
    issues = validate_report_layout(mock_report_layout, mock_model, mock_report_def)
    print(f"Total initial issues detected: {len(issues)}")
    for issue in issues:
        print(f"- Visual: {issue['visual']} | {issue['status']}: {issue['issue']}")
        
    assert len(issues) > 0, "Expected layout issues in initial model"
    assert any("FactObservation" in i["issue"] for i in issues), "Expected FactObservation table error"
    assert any("Total Organization Determinations" in i["issue"] for i in issues), "Expected measure existence error"
    assert any("limit: 1" in i["recommendation"] or "exactly 1 measure" in i["issue"] for i in issues), "Expected card properties error"
    assert any("0 dimensions" in i["issue"] for i in issues), "Expected chart dimensions error"

    print("\nAll tests completed successfully!")


if __name__ == "__main__":
    test_validator()
