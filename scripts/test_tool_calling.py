"""
Test Tool Calling — Groq llama-3.3-70b
Script standalone pour valider que le LLM choisit correctement
entre search_docs (RAG) et execute_sql (SQL).

Usage :
    python scripts/test_tool_calling.py

Ce script n'impacte pas le projet existant.
Il teste uniquement la capacité du LLM à :
    1. Choisir le bon tool selon la question
    2. Construire les bons paramètres
"""

import json
import os
import sys
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL  = "llama-3.3-70b-versatile"

# ── Définition des tools ───────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": (
                "Execute a SQL SELECT query on the Odoo PostgreSQL database "
                "to retrieve business data : sales, invoices, customers, "
                "products, employees, stock, purchases, CRM leads. "
                "Use this when the user asks for numbers, lists, counts, "
                "totals or any factual data from the database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Valid PostgreSQL SELECT query. "
                            "Always use table aliases. "
                            "product_template.name is JSONB : "
                            "use COALESCE(pt.name->>'fr_FR', pt.name->>'en_US'). "
                            "Sales : sale_order WHERE state IN ('sale','done'). "
                            "Invoices : account_move WHERE move_type='out_invoice' "
                            "AND state='posted'."
                        ),
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Short explanation of what this query retrieves.",
                    },
                },
                "required": ["query", "explanation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": (
                "Search the Odoo 16 official documentation to answer "
                "procedural or configuration questions : how to configure, "
                "how to install, how to use a feature, what are the steps, "
                "best practices. "
                "Use this when the user asks HOW to do something in Odoo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": (
                            "Search query in English optimized for "
                            "documentation retrieval."
                        ),
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Why this question requires documentation search.",
                    },
                },
                "required": ["search_query", "explanation"],
            },
        },
    },
]

SYSTEM = """You are an Odoo 16 AI assistant with access to two tools:
- execute_sql   : to retrieve data from the Odoo database
- search_docs   : to answer questions about Odoo configuration and usage

Always use the most appropriate tool. Never answer from memory alone when a tool can provide accurate data."""

# ── Questions de test ──────────────────────────────────────────────────────

TEST_QUESTIONS = [
    # SQL attendu
    ("SQL", "Combien de clients avons-nous ?"),
    ("SQL", "Quel est le chiffre d'affaires total ?"),
    ("SQL", "Liste des factures impayées"),
    ("SQL", "Top 5 produits les plus vendus"),
    ("SQL", "Combien d'employés par département ?"),
    # RAG attendu
    ("RAG", "Comment configurer la comptabilité dans Odoo ?"),
    ("RAG", "How to create a sales order in Odoo ?"),
    ("RAG", "Comment installer le module inventaire ?"),
    ("RAG", "What are the steps to configure a payment provider ?"),
    # Ambigus — on observe le choix du LLM
    ("???", "Montre-moi les ventes du mois dernier"),
    ("???", "Comment voir les factures impayées ?"),
]

# ── Couleurs terminal ──────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def call_with_tools(question: str) -> dict:
    """
    Envoie la question au LLM avec les tools disponibles.
    Retourne le résultat structuré.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": question},
        ],
        tools=TOOLS,
        tool_choice="auto",
        temperature=0,
        max_tokens=300,
    )

    message = response.choices[0].message

    # Cas 1 : le LLM a choisi un tool
    if message.tool_calls:
        tool_call = message.tool_calls[0]
        return {
            "tool_chosen": tool_call.function.name,
            "arguments":   json.loads(tool_call.function.arguments),
            "text":        None,
        }

    # Cas 2 : le LLM a répondu directement (pas de tool choisi)
    return {
        "tool_chosen": None,
        "arguments":   {},
        "text":        message.content,
    }


def _tool_to_agent(tool_name: str) -> str:
    mapping = {"execute_sql": "SQL", "search_docs": "RAG"}
    return mapping.get(tool_name, "NONE")


def run_tests():
    print(f"\n{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}  Tool Calling Test — Groq {MODEL}{RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")

    results = {"correct": 0, "wrong": 0, "ambiguous": 0, "no_tool": 0}

    for expected_agent, question in TEST_QUESTIONS:
        print(f"{BLUE}Q:{RESET} {question}")

        try:
            result      = call_with_tools(question)
            tool_chosen = result["tool_chosen"]
            args        = result["arguments"]

            if tool_chosen is None:
                print(f"  {YELLOW}⚠ Pas de tool choisi — réponse directe :{RESET}")
                print(f"  {result['text'][:120]}...")
                results["no_tool"] += 1

            else:
                agent_chosen = _tool_to_agent(tool_chosen)

                # Afficher le choix
                color = GREEN if (
                    expected_agent == "???" or agent_chosen == expected_agent
                ) else RED

                status = (
                    "✓" if agent_chosen == expected_agent
                    else "?" if expected_agent == "???"
                    else "✗"
                )

                print(
                    f"  {color}{BOLD}{status} Tool :{RESET} "
                    f"{color}{tool_chosen}{RESET} "
                    f"(attendu : {expected_agent})"
                )

                # Afficher les paramètres
                if tool_chosen == "execute_sql":
                    print(f"  {BOLD}SQL :{RESET} {args.get('query', '')[:100]}...")
                    print(f"  {BOLD}Explication :{RESET} {args.get('explanation', '')}")
                elif tool_chosen == "search_docs":
                    print(f"  {BOLD}Query doc :{RESET} {args.get('search_query', '')}")
                    print(f"  {BOLD}Explication :{RESET} {args.get('explanation', '')}")

                # Comptabiliser
                if expected_agent == "???":
                    results["ambiguous"] += 1
                elif agent_chosen == expected_agent:
                    results["correct"] += 1
                else:
                    results["wrong"] += 1

        except Exception as e:
            print(f"  {RED}✗ Erreur : {e}{RESET}")
            results["wrong"] += 1

        print()

    # ── Résumé ──────────────────────────────────────────────────────────
    total_evaluated = results["correct"] + results["wrong"]
    accuracy = (
        results["correct"] / total_evaluated * 100
        if total_evaluated > 0 else 0
    )

    print(f"{BOLD}{'='*65}{RESET}")
    print(f"{BOLD}  Résultats{RESET}")
    print(f"{BOLD}{'='*65}{RESET}")
    print(f"  {GREEN}✓ Corrects  : {results['correct']}{RESET}")
    print(f"  {RED}✗ Incorrects : {results['wrong']}{RESET}")
    print(f"  {YELLOW}? Ambigus   : {results['ambiguous']}{RESET}")
    print(f"  {YELLOW}⚠ Pas de tool : {results['no_tool']}{RESET}")
    print(f"  {BOLD}Précision   : {accuracy:.0f}% ({results['correct']}/{total_evaluated}){RESET}")
    print(f"{BOLD}{'='*65}{RESET}\n")


if __name__ == "__main__":
    run_tests()
