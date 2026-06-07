"""
Relationship Validator Module for Analytics Models.

Performs 7 checks on star schema relationships to ensure they produce
a valid, high-performance, and conflict-free Power BI semantic model.
"""

from typing import Any, Dict, List, Set, Tuple


def validate_relationships(model_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Validate the relationships of an analytics model against Power BI compatibility rules.

    Args:
        model_data: The analytics model dictionary loaded from analytics_model.json.

    Returns:
        A list of dictionary objects, each representing an issue or validation result:
        {
            "relationship": str,
            "status": str,       # "Success" | "Warning" | "Error"
            "issue": str,
            "recommendation": str
        }
    """
    issues = []
    
    # ── Load and Normalize Data ──────────────────────────────────────
    fact_tables = model_data.get("fact_tables", [])
    dim_tables = model_data.get("dimension_tables", [])
    relationships = model_data.get("relationships", [])

    # Map table names to their columns for quick lookup
    table_columns = {}
    fact_names = set()
    dim_names = set()

    for fact in fact_tables:
        name = fact.get("name", "")
        fact_names.add(name)
        table_columns[name] = {col.get("name"): col for col in fact.get("columns", [])}

    for dim in dim_tables:
        name = dim.get("name", "")
        dim_names.add(name)
        table_columns[name] = {col.get("name"): col for col in dim.get("columns", [])}

    all_table_names = fact_names.union(dim_names)

    # If no relationships are defined, check is successful but empty
    if not relationships:
        return issues

    # ── Step 0: Precompute Active Status of Relationships ──────────
    # Following the pbip_generator.py logic:
    # First relationship between a (fact_table, dimension_table) pair is active.
    # Subsequent ones are inactive.
    active_rels = []
    seen_pairs = set()
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        pair_key = (ft, dt)
        
        is_active = rel.get("is_active", True) and pair_key not in seen_pairs
        seen_pairs.add(pair_key)
        
        active_rels.append({
            **rel,
            "is_active": is_active
        })

    # ── Check 1: Duplicate Relationships ────────────────────────────
    # Look for exact duplicates: same fact_table, dimension_table, join_key
    seen_exact_rels = {}
    for idx, rel in enumerate(relationships):
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        
        key = (ft, dt, jk)
        if key in seen_exact_rels:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Error",
                "issue": f"Duplicate relationship definition detected between '{ft}' and '{dt}' on join key '{jk}'.",
                "recommendation": "Remove the duplicate relationship entry from the analytics model schema."
            })
        seen_exact_rels[key] = idx

    # ── Check 5: Fact-to-Fact Relationships ─────────────────────────
    # star schemas should not connect fact tables directly
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        
        if ft in fact_names and dt in fact_names:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Warning",
                "issue": f"Fact-to-fact relationship detected between '{ft}' and '{dt}'.",
                "recommendation": "Avoid direct relationships between fact tables. Use conformed (shared) dimensions to filter both tables, or combine them if they represent the same grain."
            })

    # ── Check 6: Missing Dimension Keys ─────────────────────────────
    # Verify that tables and join keys exist
    for rel in active_rels:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        
        # Check if tables exist
        if ft not in all_table_names:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Error",
                "issue": f"Fact table '{ft}' is referenced in relationships but is not defined in the model.",
                "recommendation": f"Add '{ft}' to the fact_tables list in the model schema."
            })
            continue

        if dt not in all_table_names:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Error",
                "issue": f"Dimension table '{dt}' is referenced in relationships but is not defined in the model.",
                "recommendation": f"Add '{dt}' to the dimension_tables list in the model schema."
            })
            continue

        # Check if join_key exists in fact table
        if jk not in table_columns[ft]:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Error",
                "issue": f"Join key column '{jk}' is missing from fact table '{ft}'.",
                "recommendation": f"Ensure the column '{jk}' is defined in the column list of fact table '{ft}'."
            })

        # Check for corresponding primary key in dimension table
        # Dimension key is either matching name, or the first column in the dimension
        dim_cols = list(table_columns[dt].keys())
        if not dim_cols:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Error",
                "issue": f"Dimension table '{dt}' has no columns defined.",
                "recommendation": f"Define columns (including the primary key) for dimension table '{dt}'."
            })
        else:
            dim_key = jk if jk in table_columns[dt] else dim_cols[0]
            if dim_key not in table_columns[dt]:
                issues.append({
                    "relationship": f"{ft}[{jk}] -> {dt}[{dim_key}]",
                    "status": "Error",
                    "issue": f"Inferred primary key '{dim_key}' is missing from dimension table '{dt}'.",
                    "recommendation": f"Ensure column '{dim_key}' is present in table '{dt}' as a primary key."
                })

    # ── Check 7: Invalid Cardinality ────────────────────────────────
    valid_cardinalities = {"many-to-one", "one-to-many", "one-to-one", "many-to-many"}
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        jk = rel.get("join_key", "")
        card = rel.get("relationship_type", "many-to-one")
        
        if card not in valid_cardinalities:
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Error",
                "issue": f"Relationship cardinality '{card}' is invalid.",
                "recommendation": f"Change relationship cardinality to one of: {', '.join(valid_cardinalities)}."
            })
        
        # Check standard star schema conventions (Fact-to-Dimension should be many-to-one)
        if ft in fact_names and dt in dim_names and card != "many-to-one":
            issues.append({
                "relationship": f"{ft}[{jk}] -> {dt}",
                "status": "Warning",
                "issue": f"Relationship from fact table '{ft}' to dimension '{dt}' is '{card}'. Star schemas expect 'many-to-one'.",
                "recommendation": "Invert relationship direction or change cardinality to 'many-to-one' to follow standard star schema modeling guidelines."
            })

    # ── Check 3: Circular Dependencies (Directed Cycles) ─────────────
    # Treat relationships as directed edges: fact_table -> dimension_table
    directed_adj = {}
    for tbl in all_table_names:
        directed_adj[tbl] = []

    for rel in active_rels:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        if ft in directed_adj and dt in directed_adj:
            directed_adj[ft].append(dt)

    # Directed DFS Cycle Detection
    visited = {}
    rec_stack = set()
    cycles = []

    def dfs_directed(node, path):
        visited[node] = True
        rec_stack.add(node)
        path.append(node)
        
        for neighbor in directed_adj.get(node, []):
            if neighbor not in visited:
                dfs_directed(neighbor, path)
            elif neighbor in rec_stack:
                # Cycle found! Extract the cycle path
                cycle_start_idx = path.index(neighbor)
                cycle_path = path[cycle_start_idx:] + [neighbor]
                cycles.append(cycle_path)
        
        rec_stack.remove(node)
        path.pop()

    for node in all_table_names:
        if node not in visited:
            dfs_directed(node, [])

    for cycle in cycles:
        cycle_str = " -> ".join(cycle)
        issues.append({
            "relationship": cycle_str,
            "status": "Error",
            "issue": f"Circular dependency (directed cycle) detected: {cycle_str}.",
            "recommendation": "Break the circular reference loop. Directed cycles are strictly forbidden in Power BI semantic models."
        })

    # ── Check 4: Multiple Active Paths (Directed Path Ambiguity) ──────
    active_directed_adj = {tbl: [] for tbl in all_table_names}
    for rel in active_rels:
        if not rel.get("is_active", True):
            continue
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        if ft in active_directed_adj and dt in active_directed_adj:
            active_directed_adj[dt].append(ft)

    def find_all_active_paths(start, end, current_path=None):
        if current_path is None:
            current_path = []
        current_path = current_path + [start]
        if start == end:
            return [current_path]
        if start not in active_directed_adj:
            return []
        paths = []
        for neighbor in active_directed_adj[start]:
            if neighbor not in current_path:
                new_paths = find_all_active_paths(neighbor, end, current_path)
                for p in new_paths:
                    paths.append(p)
        return paths

    # Check for active path conflicts
    active_conflicts = set()
    for src in all_table_names:
        for dest in all_table_names:
            if src == dest:
                continue
            all_paths = find_all_active_paths(src, dest)
            if len(all_paths) > 1:
                conflict_key = (src, dest, tuple(tuple(p) for p in all_paths))
                active_conflicts.add(conflict_key)

    for src, dest, conflict_paths in active_conflicts:
        path_strs = [" -> ".join(p) for p in conflict_paths]
        issues.append({
            "relationship": f"{src} -> {dest}",
            "status": "Error",
            "issue": f"Multiple active filtering paths exist between '{src}' and '{dest}': {'; '.join(path_strs)}.",
            "recommendation": f"Mark at least one relationship along these paths as inactive to ensure a single active filtering path."
        })

    # ── Check 2: Ambiguous Relationship Paths (Directed Path Ambiguity across ALL Relationships) ──
    all_directed_adj = {tbl: [] for tbl in all_table_names}
    for rel in relationships:
        ft = rel.get("fact_table", "")
        dt = rel.get("dimension_table", "")
        if ft in all_directed_adj and dt in all_directed_adj:
            all_directed_adj[dt].append(ft)

    def find_all_paths(start, end, current_path=None):
        if current_path is None:
            current_path = []
        current_path = current_path + [start]
        if start == end:
            return [current_path]
        if start not in all_directed_adj:
            return []
        paths = []
        for neighbor in all_directed_adj[start]:
            if neighbor not in current_path:
                new_paths = find_all_paths(neighbor, end, current_path)
                for p in new_paths:
                    paths.append(p)
        return paths

    all_conflicts = set()
    for src in all_table_names:
        for dest in all_table_names:
            if src == dest:
                continue
            all_paths = find_all_paths(src, dest)
            if len(all_paths) > 1:
                conflict_key = (src, dest, tuple(tuple(p) for p in all_paths))
                all_conflicts.add(conflict_key)

    active_conflict_pairs = {(c[0], c[1]) for c in active_conflicts}
    for src, dest, conflict_paths in all_conflicts:
        if (src, dest) in active_conflict_pairs:
            continue
        path_strs = [" -> ".join(p) for p in conflict_paths]
        issues.append({
            "relationship": f"{src} -> {dest}",
            "status": "Warning",
            "issue": f"Ambiguous relationship paths exist between '{src}' and '{dest}' in the overall model: {'; '.join(path_strs)}.",
            "recommendation": "Ensure only one path is active and resolve others via inactive relationships and DAX USERELATIONSHIP."
        })

    return issues
