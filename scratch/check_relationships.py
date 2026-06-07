import json
import glob
import os
from collections import defaultdict

def check_relationships():
    # Find model.bim
    bim_files = glob.glob("output/pbip/**/*.bim", recursive=True)
    if not bim_files:
        print("No model.bim file found!")
        return

    bim_path = bim_files[0]
    print(f"Reading model.bim from: {bim_path}")

    with open(bim_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    model = data.get("model", {})
    relationships = model.get("relationships", [])

    print(f"\n--- Total Relationships Found: {len(relationships)} ---")

    # 1. Check for duplicate relationships (exact matches on columns)
    seen = {}
    duplicates = []
    for r in relationships:
        key = (r.get("fromTable"), r.get("fromColumn"), r.get("toTable"), r.get("toColumn"))
        if key in seen:
            duplicates.append((r, seen[key]))
        seen[key] = r

    if duplicates:
        print("\n[WARN] DUPLICATE RELATIONSHIPS IDENTIFIED:")
        for dup, original in duplicates:
            print(f"- Duplicate found: {dup.get('fromTable')}[{dup.get('fromColumn')}] -> {dup.get('toTable')}[{dup.get('toColumn')}]")
    else:
        print("\n[OK] No duplicate relationships (identical source/target columns) found.")

    # 2. Check for ambiguous paths: multiple active relationships between the same tables
    # In Power BI, only one relationship between any two tables can be active.
    active_pair_counts = defaultdict(list)
    for r in relationships:
        is_active = r.get("isActive", True)
        if is_active:
            # Sort the table names to handle undirected graph properties (cross-filtering can propagate)
            # Power BI doesn't allow multiple active relationships even if one-way, between same table pair.
            t1, t2 = r.get("fromTable"), r.get("toTable")
            pair = tuple(sorted([t1, t2]))
            active_pair_counts[pair].append(r)

    ambiguous = []
    for pair, rels in active_pair_counts.items():
        if len(rels) > 1:
            ambiguous.append((pair, rels))

    if ambiguous:
        print("\n[WARN] AMBIGUOUS PATHS IDENTIFIED (multiple active relationships between same tables):")
        for pair, rels in ambiguous:
            print(f"- Between {pair[0]} and {pair[1]}:")
            for r in rels:
                print(f"  * {r.get('fromTable')}[{r.get('fromColumn')}] -> {r.get('toTable')}[{r.get('toColumn')}] (Active)")
    else:
        print("\n[OK] No ambiguous paths (multiple active relationships between same tables) found.")

    # 3. Check for circular paths (cycles in active relationships)
    # Active relationships form a graph. Let's find cycles (undirected or directed).
    # Power BI tabular model relationships are directed (from many-side to one-side, filtering propagates).
    # But cycles can cause ambiguity regardless of direction. We check for cycles in both directed and undirected senses.
    adj = defaultdict(set)
    for r in relationships:
        if r.get("isActive", True):
            t1, t2 = r.get("fromTable"), r.get("toTable")
            adj[t1].add(t2)
            adj[t2].add(t1)

    visited = set()
    cycles = []

    def dfs(node, parent, path):
        visited.add(node)
        path.append(node)
        for neighbor in adj[node]:
            if neighbor != parent:
                if neighbor in path:
                    # Found cycle!
                    cycle_start_idx = path.index(neighbor)
                    cycle = path[cycle_start_idx:] + [neighbor]
                    cycles.append(cycle)
                else:
                    dfs(neighbor, node, path)
        path.pop()

    for node in list(adj.keys()):
        if node not in visited:
            dfs(node, None, [])

    if cycles:
        print("\n[WARN] CIRCULAR PATHS IDENTIFIED:")
        for c in cycles:
            print(" -> ".join(c))
    else:
        print("\n[OK] No circular paths found in active relationships.")

if __name__ == "__main__":
    check_relationships()
