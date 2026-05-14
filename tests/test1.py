"""
Script de test du resolver — à lancer depuis la racine du projet.

Usage:
    python scripts/test_resolver.py
    python scripts/test_resolver.py --query "liste des factures impayées"
"""

import argparse
import sys
import os

# Permet d'importer les modules du projet depuis la racine
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.data_agent.model_catalogue.resolver import resolve_model

# ══════════════════════════════════════════════════════
# CAS DE TEST
# ══════════════════════════════════════════════════════

TEST_CASES = [
    # (query, expected_model)

    # Produits — product.template vs product.product
    ("combien de produits avons-nous dans le catalogue", "product.template"),
    ("liste tous les produits", "product.template"),
    ("prix du produit Chaise Bureau", "product.template"),
    ("produits de la catégorie Électronique", "product.template"),
    ("est-ce que le produit X existe", "product.template"),
    ("variante bleue du produit T-shirt", "product.product"),
    ("quelles variantes existent pour le produit Y", "product.product"),
    ("SKU de la variante taille L couleur rouge", "product.product"),
    ("référence interne de la variante XL", "product.product"),
    ("variant with size M of product Z", "product.product"),

    # Ventes
    ("liste des commandes clients ce mois", "sale.order"),
    ("quels produits ont été vendus dans la commande SO001", "sale.order.line"),
    ("nombre de devis confirmés", "sale.order"),

    # Achats
    ("bons de commande en attente fournisseur", "purchase.order"),
    ("articles commandés chez le fournisseur X", "purchase.order.line"),

    # Facturation
    ("factures impayées ce mois", "account.move"),
    ("avoirs clients", "account.move"),
    ("paiements reçus cette semaine", "account.payment"),
    ("écritures comptables de janvier", "account.move"),
    ("plan comptable", "account.account"),
    ("taux de TVA appliqués", "account.tax"),
    ("configuration des journaux", "account.journal"),

    # Employés
    ("nombre d'employés par département", "hr.employee"),
    ("liste des départements", "hr.department"),
    ("salaire contractuel de Ahmed", "hr.contract"),
    ("fiche de paie de janvier", "hr.payslip"),

    # Congés
    ("qui est en congé cette semaine", "hr.leave"),
    ("solde de congés de l'employé X", "hr.leave.allocation"),

    # Projet & Tâches
    ("liste des projets en cours", "project.project"),
    ("tâches assignées à moi", "project.task"),
    ("tâches en retard", "project.task"),

    # Contacts
    ("liste des clients actifs", "res.partner"),
    ("adresse du fournisseur Y", "res.partner"),

    # Anglais & Arabe translitéré
    ("unpaid invoices this month", "account.move"),
    ("list of employees", "hr.employee"),
]

# ══════════════════════════════════════════════════════
# COULEURS TERMINAL
# ══════════════════════════════════════════════════════

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def run_tests():
    passed = 0
    failed = 0
    errors = 0

    print(f"\n{BOLD}{'─'*70}{RESET}")
    n_product = sum(1 for _, m in TEST_CASES if m in ("product.template", "product.product"))
    print(f"{BOLD}  Resolver Test Suite — {len(TEST_CASES)} cas  "
          f"(dont {n_product} product.template / product.product){RESET}")
    print(f"{BOLD}{'─'*70}{RESET}\n")

    for query, expected in TEST_CASES:
        try:
            result = resolve_model(query)
            if result == expected:
                status = f"{GREEN}✓ PASS{RESET}"
                passed += 1
            else:
                status = f"{RED}✗ FAIL{RESET}"
                failed += 1
            print(f"  {status}  {query!r}")
            if result != expected:
                print(f"         expected : {YELLOW}{expected}{RESET}")
                print(f"         got      : {RED}{result}{RESET}")
        except Exception as exc:
            status = f"{RED}✗ ERROR{RESET}"
            errors += 1
            print(f"  {status} {query!r}")
            print(f"         {exc}")

    print(f"\n{BOLD}{'─'*70}{RESET}")
    total = passed + failed + errors
    print(f"  {GREEN}{passed}/{total} passed{RESET}  "
          f"{RED}{failed} failed{RESET}  "
          f"{RED}{errors} errors{RESET}")
    print(f"{BOLD}{'─'*70}{RESET}\n")

    return failed + errors


def run_single(query: str):
    print(f"\n  Query  : {query!r}")
    try:
        result = resolve_model(query)
        print(f"  Result : {GREEN}{result}{RESET}\n")
    except Exception as exc:
        print(f"  {RED}Error  : {exc}{RESET}\n")


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the Odoo model resolver.")
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Run a single query instead of the full test suite.",
    )
    args = parser.parse_args()

    if args.query:
        run_single(args.query)
    else:
        exit_code = run_tests()
        sys.exit(exit_code)
