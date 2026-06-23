import sys
import json
import time
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Apply Gemini API failover patch
try:
    import google.genai.models
    _original_generate_content = google.genai.models.Models.generate_content

    def patched_generate_content(self, *, model: str, contents, config=None):
        models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
        if model in models_to_try:
            models_to_try.remove(model)
            models_to_try.insert(0, model)
        else:
            models_to_try.insert(0, model)

        last_error = None
        for m in models_to_try:
            try:
                return _original_generate_content(self, model=m, contents=contents, config=config)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_quota_or_spike = any(
                    kw in err_str
                    for kw in ["quota", "exhausted", "503", "unavailable", "429", "resource_exhausted", "limit"]
                )
                if is_quota_or_spike:
                    print(f"[WARNING] Model {m} failed (quota/overload). Trying next model...")
                    time.sleep(1)
                    continue
                raise e
        raise Exception(f"All models failed. Last error: {last_error}")

    google.genai.models.Models.generate_content = patched_generate_content
except Exception as patch_err:
    print(f"Error applying patch: {patch_err}")

# Override the output and knowledge directory globally for the modules
import modules.analytics_generator as ag
project_dir = _PROJECT_ROOT / "projects" / "2680cf0a-8b1"
ag._MAPPING_CACHE_FILE = project_dir / "knowledge" / "mapping_cache.json"
ag._ANALYTICS_OUTPUT = project_dir / "output" / "analytics_model.json"

from modules.analytics_generator import generate_analytics_model, save_analytics_model

def run_test():
    print("Testing Analytics Model Regeneration with CMS-First rules...")
    
    # Load requirements and decisions
    req_path = project_dir / "output" / "requirements.json"
    dec_path = project_dir / "knowledge" / "org_decisions.json"
    
    with open(req_path, "r", encoding="utf-8") as f:
        requirements = json.load(f)
        
    with open(dec_path, "r", encoding="utf-8") as f:
        decisions = json.load(f)
        
    print("Generating analytics model via Gemini...")
    model = generate_analytics_model(requirements, decisions)
    
    print("\nGeneration Succeeded!")
    print("\nFact Tables:")
    for f in model.fact_tables:
        print(f"- {f.name} (Source: {f.source_fhir_resource})")
        print(f"  Description: {f.description}")
        print(f"  Grain: {f.grain}")
        print(f"  Columns: {[c.name for c in f.columns[:5]]}")
        
    print("\nDimension Tables:")
    for d in model.dimension_tables:
        print(f"- {d.name} (Source: {d.source_fhir_resource})")
        
    # Save model back to project directory
    save_analytics_model(model)
    print("\nSaved new analytics model to projects/2680cf0a-8b1/output/analytics_model.json")

if __name__ == "__main__":
    run_test()
