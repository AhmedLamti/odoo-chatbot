"""
Test local du data agent avec les nouveaux tools RAG.
Lance depuis la racine du projet :
    python test_agent.py
"""

import json
import sys
import os

# ── Ajoute la racine du projet au path ────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.data_agent.tools import (
    search_similar_models,
    select_models,
    get_models_schema,
)

# ═══════════════════════════════════════════════════════════
# CONFIGURATION DES TESTS
# ═══════════════════════════════════════════════════════════

QUESTIONS = [
    "Quelles sont les factures clients non payées ?",
    "Liste des bons de commande fournisseur",
    "Solde de stock disponible par produit",
    "Congés des employés en attente de validation",
    "Chiffre d'affaires par client ce mois",
]

# ═══════════════════════════════════════════════════════════
# HELPERS D'AFFICHAGE
# ═══════════════════════════════════════════════════════════

def section(title: str):
    print(f"\n{'═' * 55}")
    print(f"  {title}")
    print(f"{'═' * 55}")

def step(num: int, label: str):
    print(f"\n  {'─' * 50}")
    print(f"  Étape {num} — {label}")
    print(f"  {'─' * 50}")

def ok(msg: str):   print(f"  ✅  {msg}")
def warn(msg: str): print(f"  ⚠️   {msg}")
def err(msg: str):  print(f"  ❌  {msg}")

# ═══════════════════════════════════════════════════════════
# TEST UNITAIRE — chaque tool séparément
# ═══════════════════════════════════════════════════════════

def test_tool_1_search(question: str) -> list | None:
    """Test search_similar_models seul."""
    step(1, "search_similar_models")
    print(f"  Input  : question='{question}'")

    try:
        raw = search_similar_models.invoke({"question": question, "top_k": 8})
        candidates = json.loads(raw)

        print(f"  Output : {len(candidates)} candidats")
        for c in candidates:
            print(f"    [{c['score']:.3f}] {c['model_name']}")
            print(f"           {c['description_enrichie'][:80]}...")

        ok("search_similar_models OK")
        return candidates

    except Exception as e:
        err(f"search_similar_models FAILED : {e}")
        return None


def test_tool_2_select(question: str, candidates: list) -> list | None:
    """Test select_models seul."""
    step(2, "select_models")
    print(f"  Input  : {len(candidates)} candidats")

    try:
        raw = select_models.invoke({
            "question":   question,
            "candidates": json.dumps(candidates),
        })
        result = json.loads(raw)

        selected  = result.get("selected_models", [])
        reasoning = result.get("reasoning", "")

        print(f"  Sélection  : {selected}")
        print(f"  Raisonnement : {reasoning}")

        if not selected:
            warn("Aucun modèle sélectionné")
            return None

        ok("select_models OK")
        return selected

    except Exception as e:
        err(f"select_models FAILED : {e}")
        return None


def test_tool_3_schema(model_names: list) -> dict | None:
    """Test get_models_schema seul."""
    step(3, "get_models_schema")
    print(f"  Input  : {model_names}")

    try:
        raw = get_models_schema.invoke({"model_names": model_names})

        if raw.startswith("Erreur") or raw.startswith("Aucun"):
            err(raw)
            return None

        schema = json.loads(raw)

        for model_name, data in schema.items():
            fields = list(data["fields"].keys())
            print(f"\n  📋 {model_name}")
            print(f"     Description : {data['description']}")
            print(f"     Champs ({len(fields)}) : {fields[:6]}{'...' if len(fields) > 6 else ''}")

            # Relations many2one
            relations = {
                fname: fdata["related_model"]
                for fname, fdata in data["fields"].items()
                if fdata.get("type") in ("many2one", "many2many", "one2many")
                and "related_model" in fdata
            }
            if relations:
                print(f"     Relations : {dict(list(relations.items())[:4])}")

        ok("get_models_schema OK")
        return schema

    except Exception as e:
        err(f"get_models_schema FAILED : {e}")
        return None


# ═══════════════════════════════════════════════════════════
# TEST PIPELINE COMPLET (les 3 tools chaînés)
# ═══════════════════════════════════════════════════════════

def test_pipeline(question: str) -> bool:
    section(f"PIPELINE : {question}")

    # Étape 1
    candidates = test_tool_1_search(question)
    if not candidates:
        return False

    # Étape 2
    selected = test_tool_2_select(question, candidates)
    if not selected:
        return False

    # Étape 3
    schema = test_tool_3_schema(selected)
    if not schema:
        return False

    print(f"\n  🎯 Pipeline complet OK")
    print(f"     Question  : {question}")
    print(f"     Modèles   : {selected}")
    print(f"     Champs total : {sum(len(d['fields']) for d in schema.values())}")
    return True


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n🚀 Démarrage des tests RAG tools")
    print(f"   {len(QUESTIONS)} questions à tester\n")

    results = {}

    for question in QUESTIONS:
        success = test_pipeline(question)
        results[question] = "✅ OK" if success else "❌ FAILED"

    # ── Rapport final ──────────────────────────────────────
    section("RAPPORT FINAL")
    for question, status in results.items():
        print(f"  {status}  {question}")

    total   = len(results)
    success = sum(1 for s in results.values() if "OK" in s)
    print(f"\n  {success}/{total} tests passés\n")
