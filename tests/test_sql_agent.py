import pytest
from agents.sql_agent import SQLAgent
from tools.sql_executor import SQLExecutor

agent = SQLAgent()
executor = SQLExecutor()


# ─── Tests de sécurité ───────────────────────────────────────────

def test_sql_security_drop():
    result = executor.execute("DROP TABLE res_partner")
    assert result["success"] is False

def test_sql_security_delete():
    result = executor.execute("DELETE FROM res_partner")
    assert result["success"] is False

def test_sql_security_update():
    result = executor.execute("UPDATE res_partner SET name='test'")
    assert result["success"] is False

def test_sql_security_insert():
    result = executor.execute("INSERT INTO res_partner VALUES (1, 'test')")
    assert result["success"] is False


# ─── Tests de connexion ──────────────────────────────────────────

def test_sql_connection():
    from db.sql_connector import SQLConnector
    db = SQLConnector()
    assert db.test_connection() is True


# ─── Tests de génération SQL ─────────────────────────────────────

@pytest.mark.parametrize("question,expected_table", [
    ("Combien de clients avons-nous ?", "res_partner"),
    ("Quel est le chiffre d'affaires total ?", "sale_order"),
    ("Combien de commandes de vente avons-nous ?", "sale_order"),
    ("Liste des produits disponibles", "product_template"),
    ("Combien d'employés avons-nous ?", "hr_employee"),
    ("Liste des factures impayées", "account_move"),
])
def test_sql_generation_uses_correct_table(question, expected_table):
    result = agent.run(question)
    assert expected_table in result["sql_query"].lower(), (
        f"Question: '{question}'\n"
        f"Table attendue: {expected_table}\n"
        f"SQL généré: {result['sql_query']}"
    )


# ─── Tests de résultats ──────────────────────────────────────────

def test_sql_returns_results():
    result = agent.run("Combien de clients avons-nous ?")
    assert result["execution_result"]["success"] is True
    assert result["execution_result"]["row_count"] > 0

def test_sql_answer_not_empty():
    result = agent.run("Combien de produits avons-nous ?")
    assert result["answer"] is not None
    assert len(result["answer"]) > 0
