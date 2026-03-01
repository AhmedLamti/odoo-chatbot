import pytest
from agents.rag_agent import RAGAgent
from tools.retriever import RAGRetriever

agent = RAGAgent(top_k=5)
retriever = RAGRetriever(top_k=5)


# ─── Tests du retriever ──────────────────────────────────────────

def test_retriever_returns_results():
    results = retriever.retrieve("How to create a sales order in Odoo?")
    assert len(results) > 0

def test_retriever_results_have_content():
    results = retriever.retrieve("invoice in Odoo")
    for r in results:
        assert "content" in r
        assert len(r["content"]) > 0

def test_retriever_results_have_score():
    results = retriever.retrieve("product configuration")
    for r in results:
        assert "score" in r
        assert 0 <= r["score"] <= 1

def test_retriever_score_relevance():
    """Les résultats doivent avoir un score minimum de pertinence"""
    results = retriever.retrieve("sales order Odoo")
    assert results[0]["score"] >= 0.70


# ─── Tests du RAG Agent ──────────────────────────────────────────

@pytest.mark.parametrize("question,expected_keywords", [
    ("Comment créer une commande de vente ?", ["vente", "sale", "order"]),
    ("How to configure accounting ?", ["accounting", "comptabilité"]),
    ("Comment installer le module inventaire ?", ["inventaire", "inventory"]),
])
def test_rag_answer_contains_keyword(question, expected_keywords):
    result = agent.run(question)
    found = any(k.lower() in result["answer"].lower() for k in expected_keywords)
    assert found, (
        f"Question: '{question}'\n"
        f"Mots clés attendus: {expected_keywords}\n"
        f"Réponse: {result['answer'][:200]}"
    )

def test_rag_returns_sources():
    result = agent.run("What is Odoo?")
    assert result["sources"] is not None
    assert len(result["sources"]) > 0

def test_rag_french_question_french_answer():
    """Une question en français doit avoir une réponse en français"""
    result = agent.run("Comment configurer la comptabilité dans Odoo ?")
    # Vérifier que la réponse contient des mots français courants
    french_words = ["dans", "vous", "pour", "les", "une", "est", "avec"]
    found = any(w in result["answer"].lower() for w in french_words)
    assert found, f"Réponse pas en français: {result['answer'][:200]}"
