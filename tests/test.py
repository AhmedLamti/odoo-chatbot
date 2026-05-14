# scripts/debug_candidates.py

from agents.data_agent.model_catalogue.catalogue import model_catalogue

queries = [
    "payments received this week",
    "leave request pending validation", 
    "leave balance allocation",
    "payslip january",
    "how many orders this month",
    "items ordered from supplier",
]

for q in queries:
    print(f"\n{'='*50}")
    print(f"Query: {q}")
    results = model_catalogue.search(q, top_k=15)
    for r in results:
        print(f"  {r['score']:.3f} | {r['model']}")
