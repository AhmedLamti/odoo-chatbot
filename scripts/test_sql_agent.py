"""
Test SQL Agent — Tool Calling + MCP PostgreSQL
Valide le flow complet : question → tool calling → MCP → réponse

Usage :
    python scripts/test_sql_agent.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import SQLAgent

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

TEST_QUESTIONS = [
    "Combien de clients avons-nous ?",
    "Quel est le chiffre d'affaires total ?",
    "Liste des 5 meilleures commandes clients",
    "Combien d'employés par département ?",
    "Top 5 produits les plus vendus",
]


def run_tests():
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  SQL Agent — Tool Calling + MCP PostgreSQL{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    with SQLAgent() as agent:
        for question in TEST_QUESTIONS:
            print(f"{BLUE}Q:{RESET} {question}")

            try:
                result = agent.run(question)

                if result["error"]:
                    print(f"  {RED}✗ Erreur : {result['error']}{RESET}")
                else:
                    print(f"  {GREEN}✓ Réponse :{RESET}")
                    print(f"  {result['answer'][:300]}")

                    if result["sql_query"]:
                        print(f"  {YELLOW}SQL :{RESET} {result['sql_query'][:150]}...")

            except Exception as e:
                print(f"  {RED}✗ Exception : {e}{RESET}")

            print()

    print(f"{BOLD}{'='*60}{RESET}\n")


if __name__ == "__main__":
    run_tests()
