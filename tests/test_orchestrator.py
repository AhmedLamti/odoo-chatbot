import pytest
from agents.orchestrator import Orchestrator

orchestrator = Orchestrator()


@pytest.mark.parametrize("question,expected_agent", [
    ("Combien de clients avons-nous ?", "SQL"),
    ("Quel est le chiffre d'affaires total ?", "SQL"),
    ("Combien de commandes ce mois-ci ?", "SQL"),
    ("Liste des employés", "SQL"),
    ("Comment configurer la comptabilité ?", "RAG"),
    ("How to install inventory module ?", "RAG"),
    ("Comment créer une facture ?", "RAG"),
])
def test_routing(question, expected_agent):
    result = orchestrator.run(question)
    assert result["agent_used"] == expected_agent, (
        f"Question: '{question}'\n"
        f"Agent attendu: {expected_agent}\n"
        f"Agent utilisé: {result['agent_used']}"
    )

def test_response_not_empty():
    result = orchestrator.run("Combien de produits avons-nous ?")
    assert len(result["answer"]) > 0

def test_sql_response_has_query():
    result = orchestrator.run("Combien de clients avons-nous ?")
    assert result["sql_query"] is not None

def test_rag_response_has_sources():
    result = orchestrator.run("How to configure accounting in Odoo ?")
    assert result["sources"] is not None
