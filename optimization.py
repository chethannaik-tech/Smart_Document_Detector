def optimize_similarity_results(results):
    """
    Sort the similarity results from highest to lowest.
    """
    return sorted(
        results,
        key=lambda r: float(r["similarity_percent"]),
        reverse=True
    )


def get_similarity_statistics(results):
    if not results:
        return {
            "total": 0,
            "average": 0,
            "highest": 0,
            "flagged": 0
        }

    values = [
        float(r["similarity_percent"])
        for r in results
    ]

    return {
        "total": len(values),
        "average": round(sum(values) / len(values), 2),
        "highest": round(max(values), 2),
        "flagged": sum(1 for v in values if v >= 50)
    }