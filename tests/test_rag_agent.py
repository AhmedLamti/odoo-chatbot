import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import run_rag_agent
from agents import rewrite_query



if __name__ == "__main__":
    questions_fr = [
        "Comment créer une commande de vente dans Odoo ?",
        "Comment installer le module inventaire ?",
        "Comment configurer la comptabilité ?",
    ]

    print("\n=== Test Rewriter ===")
    for q in questions_fr:
        rewritten = rewrite_query(q)
        print(f"Original : {q}")
        print(f"Rewritten: {rewritten}\n")
    questions = [
        "Comment créer une commande de vente dans Odoo ?",
        "How to configure accounting in Odoo ?",
        "Comment installer le module inventaire ?",
        "Comment configurer la comptabilité ?",
        "How to create a purchase order ?",
    ]

    for q in questions:
        print(f"\n{'='*50}")
        print(f"Q: {q}")
        try:
            r = run_rag_agent(q)
            print(f"R: {r['answer'][:300]}...")
            print(f"Sources: {len(r['sources'])}")
            print(f"Tentatives: {r['attempts']}")
        except Exception as e:
            print(f"ERREUR: {e}")
