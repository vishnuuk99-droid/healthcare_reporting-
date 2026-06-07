import json
from pathlib import Path

output_dir = Path("output")
output_dir.mkdir(parents=True, exist_ok=True)

mock_dax = [
    {
        "measure_name": "Total Org Determinations Override",
        "business_definition": "Total count of unique Organization Determinations.",
        "dax_expression": "COUNTROWS(FactObservation)",
        "dependencies": []
    },
    {
        "measure_name": "Adverse Decision Rate",
        "business_definition": "Percentage of determinations that resulted in adverse decisions.",
        "dax_expression": "DIVIDE(CALCULATE(COUNTROWS(FactObservation), FactObservation[disposition] = \"Adverse\"), [Total Org Determinations Override], 0)",
        "dependencies": [
            "Total Org Determinations Override"
        ]
    }
]

dax_file = output_dir / "dax_artifacts.json"
with open(dax_file, "w", encoding="utf-8") as f:
    json.dump(mock_dax, f, indent=2, ensure_ascii=False)

print(f"Mock DAX saved to {dax_file.resolve()}")
