"""
Test script for verifying auto_correct_report_layout in modules/report_layout_validator.py.
"""

import sys
import json
import shutil
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from modules.report_layout_validator import auto_correct_report_layout
from modules.file_manager import OUTPUT_DIR


def test_auto_correct():
    print("Running Report Layout Auto-Correction tests...\n")

    # Define paths
    report_def_path = OUTPUT_DIR / "report_definition.json"
    measures_path = OUTPUT_DIR / "measures.json"

    # Backup files
    report_def_bak = OUTPUT_DIR / "report_definition.json.bak"
    measures_bak = OUTPUT_DIR / "measures.json.bak"

    shutil.copy(report_def_path, report_def_bak)
    shutil.copy(measures_path, measures_bak)

    try:
        # Introduce a stale reference on purpose:
        # 1. Change FactObservation to FactObservationStale in report_definition.json
        with open(report_def_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Change FactObservation.disposition -> FactObservationStale.disposition
        for p in data.get("pages", []):
            for v in p.get("visuals", []):
                dims = v.get("dimensions", [])
                new_dims = [d.replace("FactObservation", "FactObservationStale") for d in dims]
                v["dimensions"] = new_dims

        with open(report_def_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # 2. Change FactObservation to FactObservationStale in measures.json source_tables
        with open(measures_path, "r", encoding="utf-8") as f:
            meas_data = json.load(f)
        
        for m in meas_data:
            if "FactObservationStale" not in m.get("source_tables", []):
                m["source_tables"] = ["FactObservationStale"]

        with open(measures_path, "w", encoding="utf-8") as f:
            json.dump(meas_data, f, indent=2)

        # Run auto-correction
        fixes, results = auto_correct_report_layout()

        print(f"Applied {len(fixes)} auto-fixes:")
        for fix in fixes:
            print(f"- Visual: {fix['visual']} | Fix: {fix['fix_applied']}")

        # Validate that remapping occurred
        with open(report_def_path, "r", encoding="utf-8") as f:
            corrected_data = json.load(f)
        
        # Verify FactObservationStale was renamed to FactObservation
        for p in corrected_data.get("pages", []):
            for v in p.get("visuals", []):
                for d in v.get("dimensions", []):
                    assert "FactObservationStale" not in d, f"Expected FactObservationStale to be remapped in {v['title']}"

        with open(measures_path, "r", encoding="utf-8") as f:
            corrected_meas = json.load(f)

        for m in corrected_meas:
            assert "FactObservationStale" not in m.get("source_tables", []), "Expected source_tables to be remapped in measures.json"

        print("\nAuto-correction and remapping validation passed successfully!")

    finally:
        # Restore backups
        shutil.move(report_def_bak, report_def_path)
        shutil.move(measures_bak, measures_path)


if __name__ == "__main__":
    test_auto_correct()
