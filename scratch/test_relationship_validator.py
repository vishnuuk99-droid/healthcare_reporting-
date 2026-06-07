"""
Test script for testing modules/relationship_validator.py.
"""

import sys
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from modules.relationship_validator import validate_relationships


def test_validator():
    print("Running Relationship Validator tests...\n")

    # ── Test 1: Valid Star Schema Model ──────────────────────────────
    valid_model = {
        "fact_tables": [
            {
                "name": "FactEncounter",
                "columns": [
                    {"name": "encounter_key", "data_type": "INTEGER"},
                    {"name": "patient_key", "data_type": "INTEGER"},
                    {"name": "provider_key", "data_type": "INTEGER"},
                    {"name": "encounter_date", "data_type": "DATE"},
                ]
            }
        ],
        "dimension_tables": [
            {
                "name": "DimPatient",
                "columns": [
                    {"name": "patient_key", "data_type": "INTEGER"},
                    {"name": "patient_name", "data_type": "VARCHAR"},
                ]
            },
            {
                "name": "DimProvider",
                "columns": [
                    {"name": "provider_key", "data_type": "INTEGER"},
                    {"name": "provider_name", "data_type": "VARCHAR"},
                ]
            },
            {
                "name": "DimDate",
                "columns": [
                    {"name": "date_key", "data_type": "DATE"},
                    {"name": "year", "data_type": "INTEGER"},
                ]
            }
        ],
        "relationships": [
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimProvider",
                "join_key": "provider_key",
                "relationship_type": "many-to-one"
            }
        ]
    }
    
    issues = validate_relationships(valid_model)
    assert len(issues) == 0, f"Expected 0 issues, got {len(issues)}: {issues}"
    print("Test 1 (Valid Star Schema): Passed! No issues found.")

    # ── Test 2: Duplicate Relationships ─────────────────────────────
    dup_model = {
        **valid_model,
        "relationships": [
            *valid_model["relationships"],
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            }
        ]
    }
    issues = validate_relationships(dup_model)
    dups = [i for i in issues if "Duplicate" in i["issue"]]
    assert len(dups) > 0, "Expected duplicate relationship error"
    print("Test 2 (Duplicate Relationship): Passed! Detected duplicate.")

    # ── Test 3: Fact-to-Fact Relationships ──────────────────────────
    f2f_model = {
        "fact_tables": [
            {"name": "FactEncounter", "columns": [{"name": "encounter_key"}]},
            {"name": "FactObservation", "columns": [{"name": "encounter_key"}]}
        ],
        "dimension_tables": [],
        "relationships": [
            {
                "fact_table": "FactEncounter",
                "dimension_table": "FactObservation",
                "join_key": "encounter_key",
                "relationship_type": "many-to-one"
            }
        ]
    }
    issues = validate_relationships(f2f_model)
    f2f = [i for i in issues if "Fact-to-fact" in i["issue"]]
    assert len(f2f) > 0, "Expected Fact-to-Fact warning"
    print("Test 3 (Fact-to-Fact): Passed! Detected fact-to-fact connection.")

    # ── Test 4: Missing Keys ────────────────────────────────────────
    missing_key_model = {
        "fact_tables": [
            {"name": "FactEncounter", "columns": [{"name": "encounter_key"}]} # Missing patient_key
        ],
        "dimension_tables": [
            {"name": "DimPatient", "columns": [{"name": "patient_key"}]}
        ],
        "relationships": [
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            }
        ]
    }
    issues = validate_relationships(missing_key_model)
    missing = [i for i in issues if "missing from fact table" in i["issue"]]
    assert len(missing) > 0, f"Expected missing key error, got: {issues}"
    print("Test 4 (Missing Keys): Passed! Detected missing join key.")

    # ── Test 5: Circular Dependency (Directed Cycle) ────────────────
    circular_model = {
        "fact_tables": [
            {"name": "FactEncounter", "columns": [{"name": "encounter_key"}, {"name": "patient_key"}]},
            {"name": "FactObservation", "columns": [{"name": "observation_key"}, {"name": "encounter_key"}]}
        ],
        "dimension_tables": [
            {"name": "DimPatient", "columns": [{"name": "patient_key"}, {"name": "observation_key"}]}
        ],
        "relationships": [
            # FactEncounter -> DimPatient -> FactObservation -> FactEncounter
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "DimPatient",
                "dimension_table": "FactObservation",
                "join_key": "observation_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "FactObservation",
                "dimension_table": "FactEncounter",
                "join_key": "encounter_key",
                "relationship_type": "many-to-one"
            }
        ]
    }
    issues = validate_relationships(circular_model)
    cycles = [i for i in issues if "Circular dependency" in i["issue"]]
    assert len(cycles) > 0, f"Expected circular dependency error, got {issues}"
    print("Test 5 (Circular Dependency): Passed! Detected directed loop.")

    # ── Test 6: Multiple Active Paths (Undirected Loop in Active Rels) 
    multi_active_model = {
        "fact_tables": [
            {"name": "FactEncounter", "columns": [{"name": "encounter_key"}, {"name": "patient_key"}, {"name": "date_key"}]}
        ],
        "dimension_tables": [
            {"name": "DimPatient", "columns": [{"name": "patient_key"}, {"name": "date_key"}]},
            {"name": "DimDate", "columns": [{"name": "date_key"}]}
        ],
        "relationships": [
            # FactEncounter -> DimPatient (Active)
            # FactEncounter -> DimDate (Active)
            # DimPatient -> DimDate (Active)
            # This forms an undirected active cycle: FactEncounter <-> DimPatient <-> DimDate <-> FactEncounter
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimDate",
                "join_key": "date_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "DimPatient",
                "dimension_table": "DimDate",
                "join_key": "date_key",
                "relationship_type": "many-to-one"
            }
        ]
    }
    issues = validate_relationships(multi_active_model)
    active_loops = [i for i in issues if "Multiple active filtering paths" in i["issue"]]
    assert len(active_loops) > 0, f"Expected multiple active paths error, got {issues}"
    print("Test 6 (Multiple Active Paths): Passed! Detected active filtering paths.")

    print("\nAll tests passed successfully!")


if __name__ == "__main__":
    test_validator()
