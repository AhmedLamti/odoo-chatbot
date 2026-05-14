# scripts/test_resolver.py

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from agents.data_agent.model_catalogue.resolver import resolve_model

TEST_CASES = [
    # (question, modèle attendu)

    # PRODUCTS
    ("combien de produits avons nous ?",         "product.template"),
    ("liste des produits",                        "product.template"),
    ("variantes du produit X en rouge",           "product.product"),

    # SALES
    ("combien de commandes vendu ce mois ?",            "sale.order"),
    ("quels produits ont été vendus ?",           "sale.order.line"),

    # PURCHASE
    ("bons de commande fournisseur en attente",   "purchase.order"),
    ("articles commandés chez fournisseur X",     "purchase.order.line"),

    # ACCOUNTING
    ("factures impayées ce mois",                 "account.move"),
    ("avoirs clients",                            "account.move"),
    ("paiements reçus cette semaine",             "account.payment"),
    ("liste des journaux comptables",             "account.journal"),
    ("écriture de journal",                       "account.move"),
    ("taux de TVA applicable",                    "account.tax"),
    ("plan comptable",                            "account.account"),

    # HR
    ("nombre d'employés",                         "hr.employee"),
    ("liste des départements",                    "hr.department"),
    ("congés en attente de validation",           "hr.leave"),
    ("solde de congés de Ahmed",                  "hr.leave.allocation"),
    ("fiche de paie janvier",                     "hr.payslip"),
    ("salaire contractuel de l'employé X",        "hr.contract"),

    # SHARED
    ("liste des clients",                         "res.partner"),
    ("fournisseurs actifs",                       "res.partner"),
    ("utilisateurs du système",                   "res.users"),
]
EVAL_CASES = [
    # Formulations différentes des mêmes concepts
    ("montre moi tous les articles du catalogue",          "product.template"),
    ("quel est le prix du produit Y",                      "product.template"),
    ("le produit X existe en quelle taille",               "product.product"),

    ("chiffre d'affaires du mois dernier",                 "sale.order"),
    ("devis non confirmés",                                "sale.order"),
    ("quelle quantité de produit A a été vendue",          "sale.order.line"),

    ("on a reçu quoi comme marchandise ce mois",           "purchase.order"),
    ("prix d'achat des articles reçus",                    "purchase.order.line"),

    ("facture numéro INV/2024/001",                        "account.move"),
    ("montant total des avoirs de ce trimestre",           "account.move"),
    ("on a payé le fournisseur X ?",                       "account.payment"),
    ("encaissements clients cette semaine",                "account.payment"),

    ("qui est absent aujourd'hui",                         "hr.leave"),
    ("combien de jours de congé il reste à Ahmed",         "hr.leave.allocation"),
    ("bulletin de salaire de mars",                        "hr.payslip"),
    ("quel est le salaire de base de l'employé X",         "hr.contract"),

    ("adresse du client Y",                                "res.partner"),
    ("email du fournisseur Z",                             "res.partner"),
]

def run_tests():
    passed = 0
    failed = []

    for question, expected in EVAL_CASES:
        result = resolve_model(question)
        ok = result == expected
        status = "✅" if ok else "❌"
        print(f"{status} [{expected:30s}] got [{result:30s}] | {question}")
        if ok:
            passed += 1
        else:
            failed.append((question, expected, result))

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{len(TEST_CASES)} passed")

    if failed:
        print("\nFailed cases:")
        for q, exp, got in failed:
            print(f"  - \"{q}\"")
            print(f"    expected: {exp}")
            print(f"    got:      {got}")

if __name__ == "__main__":
    run_tests()
