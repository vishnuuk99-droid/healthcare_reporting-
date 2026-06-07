"""
Test script for verifying modules/star_schema_enforcer.py.
"""

import sys
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from modules.star_schema_enforcer import enforce_star_schema
from modules.relationship_validator import validate_relationships


def test_enforcer():
    print("Running Star Schema Enforcement Engine tests...\n")

    # Define a malformed model containing ALL 7 relationship issues:
    # 1. Duplicate relationships: FactEncounter -> DimPatient (twice)
    # 2. Fact-to-Fact: FactEncounter -> FactObservation
    # 3. Circular Dependency (directed cycle): FactEncounter -> DimPatient -> FactObservation -> FactEncounter
    # 4. Multiple active filtering paths: DimPatient -> FactEncounter AND DimPatient -> FactProcedure AND FactEncounter -> FactProcedure (DimPatient filters FactProcedure both directly and via FactEncounter)
    # 5. Invalid cardinality value: "one-to-many-to-many"
    # 6. Non-standard cardinality: "one-to-one" for fact-to-dimension FactEncounter -> DimProvider
    malformed_model = {
        "fact_tables": [
            {
                "name": "FactEncounter",
                "columns": [
                    {"name": "encounter_key"},
                    {"name": "patient_key"},
                    {"name": "provider_key"},
                    {"name": "encounter_date_key"},
                    {"name": "geography_key"}
                ]
            },
            {
                "name": "FactObservation",
                "columns": [
                    {"name": "observation_key"},
                    {"name": "patient_key"},
                    {"name": "encounter_key"}
                ]
            },
            {
                "name": "FactProcedure",
                "columns": [
                    {"name": "procedure_key"},
                    {"name": "patient_key"},
                    {"name": "encounter_key"}
                ]
            }
        ],
        "dimension_tables": [
            {
                "name": "DimPatient",
                "columns": [
                    {"name": "patient_key"},
                    {"name": "observation_key"},
                    {"name": "provider_key"},
                    {"name": "geography_key"}
                ]
            },
            {
                "name": "DimProvider",
                "columns": [
                    {"name": "provider_key"},
                    {"name": "patient_key"}
                ]
            },
            {
                "name": "DimGeography",
                "columns": [
                    {"name": "geography_key"}
                ]
            }
        ],
        "relationships": [
            # 1. Duplicates
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one" # Duplicate
            },
            # 2. Fact-to-Fact
            {
                "fact_table": "FactEncounter",
                "dimension_table": "FactObservation",
                "join_key": "encounter_key",
                "relationship_type": "many-to-one"
            },
            # 3. Circular dependency link (DimPatient -> DimProvider -> DimPatient)
            {
                "fact_table": "DimPatient",
                "dimension_table": "DimProvider",
                "join_key": "provider_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "DimProvider",
                "dimension_table": "DimPatient",
                "join_key": "patient_key",
                "relationship_type": "many-to-one"
            },
            # 4. Multiple active filtering paths (DimGeography -> FactEncounter directly vs DimGeography -> DimPatient -> FactEncounter)
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimGeography",
                "join_key": "geography_key",
                "relationship_type": "many-to-one"
            },
            {
                "fact_table": "DimPatient",
                "dimension_table": "DimGeography",
                "join_key": "geography_key",
                "relationship_type": "many-to-one"
            },
            # 5. Invalid Cardinality value
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimProvider",
                "join_key": "provider_key",
                "relationship_type": "one-to-many-to-many"
            },
            # 6. Non-standard Cardinality for Fact-to-Dimension
            {
                "fact_table": "FactEncounter",
                "dimension_table": "DimProvider",
                "join_key": "provider_key",
                "relationship_type": "one-to-one"
            }
        ]
    }

    print("Auditing malformed model...")
    issues = validate_relationships(malformed_model)
    print(f"Total initial issues detected: {len(issues)}")
    assert len(issues) > 0, "Expected relationship issues in initial model"

    print("\nRunning Auto-Correction Engine...")
    corrected_model, fixes = enforce_star_schema(malformed_model)
    
    print(f"Total fixes applied: {len(fixes)}")
    for fix in fixes:
        print(f"- Fixed: {fix['issue']} -> {fix['auto_fix']}")

    # Assert that fixes were applied for all expected issues
    assert any("Duplicate" in f["issue"] for f in fixes), "Expected Duplicate fix"
    assert any("fact-to-fact" in f["issue"] for f in fixes), "Expected Fact-to-Fact fix"
    assert any("Circular" in f["issue"] for f in fixes), "Expected Circular dependency fix"
    assert any("active filtering paths" in f["issue"] for f in fixes), "Expected Multiple active paths fix"
    assert any("cardinality" in f["issue"] for f in fixes), "Expected Cardinality correction fix"

    print("\nAuditing corrected model...")
    new_issues = validate_relationships(corrected_model)
    critical_errors = [i for i in new_issues if i["status"] == "Error"]
    
    print(f"Remaining issues: {len(new_issues)} (Errors: {len(critical_errors)})")
    for issue in new_issues:
        print(f"- {issue['status']}: {issue['issue']}")
        
    assert len(critical_errors) == 0, f"Corrected model still contains critical errors: {critical_errors}"
    print("\nAll tests completed successfully!")


if __name__ == "__main__":
    test_enforcer()
