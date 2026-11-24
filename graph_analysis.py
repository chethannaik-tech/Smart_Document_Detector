def analyze_graph(results):
    graph = {}

    for r in results:
        a = r["student1"]
        b = r["student2"]
        value = float(r["similarity_percent"])

        graph.setdefault(a, [])
        graph.setdefault(b, [])

        graph[a].append((b, value))
        graph[b].append((a, value))

    nodes = list(graph.keys())
    edges = []

    for a in graph:
        for b, value in graph[a]:
            if a < b:
                edges.append({
                    "source": a,
                    "target": b,
                    "weight": value
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges)
    }


def high_similarity_pairs(results, threshold=50):
    return [
        r for r in results
        if float(r["similarity_percent"]) >= threshold
    ]