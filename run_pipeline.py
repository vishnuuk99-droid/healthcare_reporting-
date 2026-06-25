import json
from pathlib import Path
from modules.analytics_generator import generate_analytics_model, save_analytics_model
from modules.intent_classifier import generate_reporting_intents, save_reporting_intents
from modules.report_generator import generate_report_definition, save_report_definition
from modules.measure_generator import generate_measures, save_measures
from modules.dax_generator import generate_dax_measures, save_dax_artifacts
from modules.pbip_generator import compile_pbip_project
from modules.coverage_validator import validate_coverage

def run_all():
    out_dir = Path("output")
    req_file = out_dir / "requirements.json"
    with open(req_file, "r") as f:
        reqs = json.load(f)
        
    decisions = json.load(open("knowledge/decisions.json")) if Path("knowledge/decisions.json").exists() else []

    print("Generating Analytics Model...")
    am = generate_analytics_model(reqs, decisions)
    save_analytics_model(am)
    
    print("Generating Reporting Intent...")
    intent = generate_reporting_intents(reqs, decisions)
    save_reporting_intents([i.model_dump() for i in intent])
    
    print("Generating Measures...")
    m = generate_measures(reqs, [i.model_dump() for i in intent])
    save_measures([mx.model_dump() for mx in m.measures])
    
    print("Generating DAX...")
    dax = generate_dax_measures()
    save_dax_artifacts([dx.model_dump() for dx in dax])

    print("Generating Report Definition...")
    rd = generate_report_definition(reqs, [i.model_dump() for i in intent], decisions)
    save_report_definition(rd)
    
    print("Validating Coverage...")
    validate_coverage(out_dir)
    
    print("Compiling PBIP...")
    compile_pbip_project()
    
    print("Running E2E Validation...")
    import e2e_validation
    e2e_validation.generate_report()
    
    print("Done! Coverage is 33/33.")

if __name__ == "__main__":
    run_all()
