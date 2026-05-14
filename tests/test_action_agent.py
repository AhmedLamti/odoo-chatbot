import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.action_agent.node import run_action_agent


def test_find_partner():
    r = run_action_agent(
        "Trouve le client Azure Interior",
        session_id="test1"
    )
    print(f"\nR: {r['answer']}")
    assert len(r["answer"]) > 0


def test_create_employee():
    r = run_action_agent(
        "Crée un employé nommé Ahmed Lamti avec le poste Développeur dans le département R&D",
        session_id="test2"
    )
    print(f"\nR: {r['answer']}")
    print(f"Needs confirmation: {r['needs_confirmation']}")
    assert r["needs_confirmation"] is True


def test_create_sale_order():
    r = run_action_agent(
        "Crée une commande pour Azure Interior avec 2 unités du produit Cabinet",
        session_id="test3"
    )
    print(f"\nR: {r['answer']}")
    print(f"Needs confirmation: {r['needs_confirmation']}")
    assert r["needs_confirmation"] is True


if __name__ == "__main__":
    tests = [
        ("Trouve le client Azure Interior", "s1"),
        ("Crée un employé nommé Test User au département Sales", "s2"),
        ("Crée une commande pour Azure Interior avec 1 unité du produit Cabinet", "s3"),
        ("Mets à jour le prix du produit Cabinet à 350 €", "s4"),
    ]

    for question, sid in tests:
        print(f"\n{'='*50}")
        print(f"Q: {question}")
        try:
            r = run_action_agent(question, session_id=sid)
            print(f"R: {r['answer']}")
            print(f"Confirmation needed: {r['needs_confirmation']}")
        except Exception as e:
            print(f"ERREUR: {e}")
