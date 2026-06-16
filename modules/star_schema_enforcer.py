"""
Star Schema Enforcement Engine.

Audits generated analytics models against Power BI relationship compatibility rules
and automatically corrects any violations before PBIP compilation.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from modules.file_manager import OUTPUT_DIR
from modules.pbip_generator import compile_pbip_project, validate_pbip_project

_ANALYTICS_MODEL_FILE = OUTPUT_DIR / "analytics_model.json"


def enforce_star_schema(model_data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """
    Audit and auto-correct relationship violations in the analytics model.

    Args:
        model_data: The analytics model dictionary loaded from analytics_model.json.

    Returns:
        corrected_model: The updated model dictionary with corrected relationships.
        applied_fixes: A list of auto-fixes applied, in the requested format:
        {
            "issue": str,
            "severity": str,
            "auto_fix": str,
            "status": str
        }
    """
    corrected_model = json.loads(json.dumps(model_data)) # Deep copy
    applied_fixes = []

    fact_tables = corrected_model.get("fact_tables", [])
    dim_tables = corrected_model.get("dimension_tables", [])
    relationships = corrected_model.get("relationships", [])

    fact_names = {f.get("name", "") for f in fact_tables}
    dim_names = {d.get("name", "") for d in dim_tables}
    all_table_names = fact_names.union(dim_names)

    # ── Rule 5: Detect and Remove Duplicate Relationship Routes ──────
    unique_rels = []
    seen_keys = set()
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        
        key = (ft, dt, jk)
        if key in seen_keys:
            applied_fixes.append({
                "issue": f"Duplicate relationship route detected between '{ft}' and '{dt}' on key '{jk}'.",
                "severity": "Error",
                "auto_fix": f"Removed duplicate relationship route '{ft}[{jk}] -> {dt}'.",
                "status": "Fixed"
            })
        else:
            seen_keys.add(key)
            unique_rels.append(rel)
    
    relationships = unique_rels

    # ── Rule 1 & 2: No Fact-to-Fact Relationships ───────────────────
    # Facts may only connect through dimensions.
    filtered_rels = []
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        
        if ft in fact_names and dt in fact_names:
            applied_fixes.append({
                "issue": f"Direct fact-to-fact relationship detected: '{ft}' -> '{dt}'.",
                "severity": "Error",
                "auto_fix": f"Removed direct relationship '{ft}[{jk}] -> {dt}' to ensure facts connect only through shared dimensions.",
                "status": "Fixed"
            })
        else:
            filtered_rels.append(rel)

    relationships = filtered_rels

    # ── Rule 7 & 3: Validate Cardinality & Star Schema Card ─────────
    # Cardinality must be valid and fact-to-dimension must be many-to-one (one-to-many from dim to fact).
    valid_cardinalities = {"many-to-one", "one-to-many", "one-to-one", "many-to-many"}
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        card = rel.get("relationship_type", "many-to-one")
        
        # Rule 7: Validate Cardinality values
        if card not in valid_cardinalities:
            rel["relationship_type"] = "many-to-one"
            applied_fixes.append({
                "issue": f"Invalid relationship cardinality '{card}' on '{ft}' -> '{dt}'.",
                "severity": "Error",
                "auto_fix": f"Reset relationship cardinality to standard 'many-to-one'.",
                "status": "Fixed"
            })
            
        # Rule 3: Fact-to-Dimension must be many-to-one
        elif ft in fact_names and dt in dim_names and card != "many-to-one":
            rel["relationship_type"] = "many-to-one"
            applied_fixes.append({
                "issue": f"Non-standard cardinality '{card}' on fact-to-dimension '{ft}' -> '{dt}'. Star schema expects many-to-one.",
                "severity": "Warning",
                "auto_fix": f"Corrected cardinality from '{card}' to 'many-to-one'.",
                "status": "Fixed"
            })

    # ── Rule 6: Detect and Resolve Circular Dependencies ────────────
    # DFS cycle detection on directed graph of relationships (from Fact to Dimension)
    # We run in a loop to resolve all cycles.
    while True:
        directed_adj = {tbl: [] for tbl in all_table_names}
        for rel in relationships:
            ft = rel.get("fact_table", "")
            dt = rel.get("dimension_table", "")
            if ft in directed_adj and dt in directed_adj:
                directed_adj[ft].append((dt, rel))

        visited = {}
        rec_stack = set()
        detected_cycle_rel = None

        def dfs_find_cycle(node, path):
            nonlocal detected_cycle_rel
            if detected_cycle_rel:
                return
            visited[node] = True
            rec_stack.add(node)
            
            for neighbor, rel in directed_adj.get(node, []):
                if neighbor not in visited:
                    dfs_find_cycle(neighbor, path + [rel])
                elif neighbor in rec_stack:
                    # Found a cycle! Save the last relationship that forms the cycle
                    detected_cycle_rel = rel
                    return
            
            rec_stack.remove(node)

        for node in all_table_names:
            if node not in visited and not detected_cycle_rel:
                dfs_find_cycle(node, [])

        if detected_cycle_rel:
            ft = detected_cycle_rel.get("fact_table", "")
            dt = detected_cycle_rel.get("dimension_table", "")
            jk = detected_cycle_rel.get("join_key", "")
            
            relationships.remove(detected_cycle_rel)
            applied_fixes.append({
                "issue": f"Circular dependency (directed cycle) loop detected involving relationship '{ft}[{jk}] -> {dt}'.",
                "severity": "Error",
                "auto_fix": f"Removed relationship '{ft}[{jk}] -> {dt}' to break the directed circular reference loop.",
                "status": "Fixed"
            })
        else:
            break

    # ── Rule 4: Only One Active Relationship Path Between Two Tables ──
    # Trace active filtering paths (directed edges from dimension to fact).
    # If multiple active paths exist, we deactivate one of the relationships.
    while True:
        # Precompute active relationships (first relationship per table pair is active unless marked inactive)
        seen_pairs = set()
        active_rels = []
        for rel in relationships:
            if not rel.get("is_active", True):
                continue
            ft = rel.get("fact_table", "")
            dt = rel.get("dimension_table", "")
            pair_key = (ft, dt)
            if pair_key not in seen_pairs:
                seen_pairs.add(pair_key)
                active_rels.append(rel)

        # Build directed graph of active relationships where filters propagate (dim -> fact)
        active_directed_adj = {tbl: [] for tbl in all_table_names}
        for rel in active_rels:
            ft = rel.get("fact_table", "")
            dt = rel.get("dimension_table", "")
            if ft in active_directed_adj and dt in active_directed_adj:
                active_directed_adj[dt].append((ft, rel))

        def find_all_active_paths(start, end, visited_nodes=None, current_path=None):
            if visited_nodes is None:
                visited_nodes = {start}
            if current_path is None:
                current_path = []
                
            if start == end:
                return [current_path]
                
            if start not in active_directed_adj:
                return []
                
            paths = []
            for neighbor, rel in active_directed_adj[start]:
                if neighbor not in visited_nodes:
                    new_paths = find_all_active_paths(
                        neighbor, 
                        end, 
                        visited_nodes.union({neighbor}), 
                        current_path + [rel]
                    )
                    for p in new_paths:
                        paths.append(p)
            return paths

        conflict_found = False
        for src in all_table_names:
            for dest in all_table_names:
                if src == dest:
                    continue
                paths = find_all_active_paths(src, dest)
                if len(paths) > 1:
                    # Conflict! Deactivate one of the relationships
                    # Prefer deactivating a direct relationship if one exists, otherwise the first relationship in the second path.
                    direct_rel = None
                    for neighbor, rel in active_directed_adj.get(src, []):
                        if neighbor == dest:
                            direct_rel = rel
                            break
                    
                    rel_to_deactivate = direct_rel if direct_rel else paths[1][0]
                    rel_to_deactivate["is_active"] = False
                    
                    ft = rel_to_deactivate.get("fact_table", "")
                    dt = rel_to_deactivate.get("dimension_table", "")
                    jk = rel_to_deactivate.get("join_key", "")
                    
                    path_strs = []
                    for p in paths:
                        node_seq = [src]
                        for rel in p:
                            node_seq.append(rel["fact_table"])
                        path_strs.append(" -> ".join(node_seq))
                        
                    applied_fixes.append({
                        "issue": f"Multiple active filtering paths exist between '{src}' and '{dest}': {'; '.join(path_strs)}.",
                        "severity": "Error",
                        "auto_fix": f"Deactivated relationship '{ft}[{jk}] -> {dt}' (set is_active: false) to resolve ambiguity loop.",
                        "status": "Fixed"
                    })
                    conflict_found = True
                    break
            if conflict_found:
                break
        if not conflict_found:
            break

    corrected_model["relationships"] = relationships
    return corrected_model, applied_fixes


def enforce_and_regenerate() -> Dict[str, Any]:
    """
    Enforce star schema rules on output/analytics_model.json.
    Saves the corrected model, regenerates model.bim / PBIP folder structure,
    and runs PBIP validation.

    Returns:
        dict: A dictionary containing:
            "fixes": list of applied fixes
            "pbip_status": pbip validation status results
    """
    if not _ANALYTICS_MODEL_FILE.exists():
        raise FileNotFoundError("analytics_model.json does not exist. Please generate the model first.")

    with open(_ANALYTICS_MODEL_FILE, "r", encoding="utf-8") as f:
        model_data = json.load(f)

    # Run enforcement
    corrected_model, applied_fixes = enforce_star_schema(model_data)

    # Save the corrected model back to disk
    with open(_ANALYTICS_MODEL_FILE, "w", encoding="utf-8") as f:
        json.dump(corrected_model, f, indent=2)

    # Compile the PBIP project (this regenerates model.bim, model.tmdl, report.json, etc.)
    try:
        from modules.pbip_generator import PBIPValidationError
        compile_result = compile_pbip_project()
    except PBIPValidationError as e:
        compile_result = {"is_valid": False, "errors": e.errors}

    # Re-run validation
    val_result = validate_pbip_project()

    return {
        "fixes": applied_fixes,
        "compile_result": compile_result,
        "validation_result": val_result
    }
