"""
tests/test_discovery.py

Script de test autonome pour valider le comportement de :
  - discover_model(intent)     → résolution langage naturel → modèle technique
  - get_model_fields(model)    → introspection des champs d'un modèle

Aucune dépendance à LangGraph ou à l'agent ReAct.
Lance directement les outils et imprime les résultats.

Usage :
    python tests/test_discovery.py
    python tests/test_discovery.py --verbose
"""

import argparse
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any

# ── Import des outils à tester ────────────────────────────────────────────────
from agents.action_agent.tools.discovery import discover_model, get_model_fields


# ── Structure d'un cas de test ─────────────────────────────────────────────────

@dataclass
class DiscoverTestCase:
    """Un cas de test pour discover_model."""
    intent: str  # Description en langage naturel
    expected_models: list[str]  # Modèles techniques acceptables
    description: str = ""  # Explication du cas de test


@dataclass
class FieldsTestCase:
    """Un cas de test pour get_model_fields."""
    model: str  # Modèle technique à inspecter
    expected_fields: list[str]  # Champs qui doivent être présents
    description: str = ""


# ── Cas de test : discover_model ──────────────────────────────────────────────

DISCOVER_CASES: list[DiscoverTestCase] = [

    # ── Produits (cas critique : product.product vs product.template) ──────
    DiscoverTestCase(
        intent="produit",
        expected_models=["product.product", "product.template"],
        description="Terme générique 'produit' → l'un des deux modèles produit",
    ),
    DiscoverTestCase(
        intent="fiche produit",
        expected_models=["product.template"],
        description="'Fiche produit' doit pointer vers product.template (le gabarit)",
    ),
    DiscoverTestCase(
        intent="variante de produit",
        expected_models=["product.product"],
        description="'Variante' est le sens précis de product.product",
    ),
    DiscoverTestCase(
        intent="article en stock",
        expected_models=["product.product", "product.template"],
        description="'Article en stock' reste dans la famille produit",
    ),

    # ── Clients / Partenaires ──────────────────────────────────────────────
    DiscoverTestCase(
        intent="client",
        expected_models=["res.partner"],
        description="'Client' → res.partner",
    ),
    DiscoverTestCase(
        intent="contact fournisseur",
        expected_models=["res.partner"],
        description="'Fournisseur' est aussi un res.partner",
    ),

    # ── Ventes ────────────────────────────────────────────────────────────
    DiscoverTestCase(
        intent="commande client",
        expected_models=["sale.order"],
        description="'Commande client' → sale.order",
    ),
    DiscoverTestCase(
        intent="bon de commande",
        expected_models=["purchase.order"],
        description="'Bon de commande' → purchase.order",
    ),

    # ── Comptabilité ──────────────────────────────────────────────────────
    DiscoverTestCase(
        intent="facture",
        expected_models=["account.move"],
        description="'Facture' → account.move",
    ),

    # ── Cas limites ───────────────────────────────────────────────────────
    DiscoverTestCase(
        intent="employé",
        expected_models=["hr.employee"],
        description="'Employé' → hr.employee",
    ),
]

# ── Cas de test : get_model_fields ────────────────────────────────────────────

FIELDS_CASES: list[FieldsTestCase] = [
    FieldsTestCase(
        model="product.template",
        expected_fields=["name", "list_price", "categ_id", "type"],
        description="Champs de base d'un gabarit produit",
    ),
    FieldsTestCase(
        model="product.product",
        expected_fields=["name", "product_tmpl_id", "default_code"],
        description="Champs de base d'une variante produit",
    ),
    FieldsTestCase(
        model="res.partner",
        expected_fields=["name", "email", "phone", "is_company"],
        description="Champs de base d'un partenaire",
    ),
]


# ── Moteur de test ────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    details: str
    raw_output: Any = field(default=None, repr=False)


def _call_tool(tool_fn, **kwargs) -> Any:
    """Appelle un outil LangChain (tool.invoke ou appel direct)."""
    if hasattr(tool_fn, "invoke"):
        return tool_fn.invoke(kwargs)
    return tool_fn(**kwargs)


def run_discover_case(case: DiscoverTestCase, verbose: bool) -> TestResult:
    name = f"discover_model | {case.intent!r}"
    try:
        raw = _call_tool(discover_model, intent=case.intent)
        result_str = str(raw).lower()

        matched = [m for m in case.expected_models if m in result_str]
        passed = bool(matched)

        details = (
            f"✅ Résolu vers : {matched}"
            if passed
            else f"❌ Aucun modèle attendu trouvé.\n"
                 f"   Attendu : {case.expected_models}\n"
                 f"   Obtenu  : {str(raw)[:300]}"
        )

        if verbose:
            details += f"\n   Sortie brute : {str(raw)[:500]}"

        return TestResult(name=name, passed=passed, details=details, raw_output=raw)

    except Exception as exc:
        return TestResult(
            name=name, passed=False,
            details=f"💥 Exception : {exc}\n{traceback.format_exc()}"
        )


def run_fields_case(case: FieldsTestCase, verbose: bool) -> TestResult:
    name = f"get_model_fields | {case.model}"
    try:
        raw = _call_tool(get_model_fields, model=case.model)
        result_str = str(raw).lower()

        missing = [f for f in case.expected_fields if f not in result_str]
        passed = not missing

        details = (
            f"✅ Tous les champs attendus présents : {case.expected_fields}"
            if passed
            else f"❌ Champs manquants : {missing}"
        )

        if verbose:
            details += f"\n   Sortie brute (500c) : {str(raw)[:500]}"

        return TestResult(name=name, passed=passed, details=details, raw_output=raw)

    except Exception as exc:
        return TestResult(
            name=name, passed=False,
            details=f"💥 Exception : {exc}\n{traceback.format_exc()}"
        )


# ── Rapport ───────────────────────────────────────────────────────────────────

def print_report(results: list[TestResult]) -> None:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print("\n" + "═" * 60)
    print(f"  RÉSULTATS : {passed}/{total} passés  |  {failed} échecs")
    print("═" * 60)

    for r in results:
        icon = "✅" if r.passed else "❌"
        print(f"\n{icon}  {r.name}")
        for line in r.details.splitlines():
            print(f"     {line}")

    print("\n" + "═" * 60)
    if failed:
        print(f"  ⚠️  {failed} test(s) échoué(s). Voir les détails ci-dessus.")
    else:
        print("  🎉  Tous les tests sont passés.")
    print("═" * 60 + "\n")


# ── Point d'entrée ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tests discover_model / get_model_fields")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Afficher la sortie brute de chaque outil")
    parser.add_argument("--only", choices=["discover", "fields"],
                        help="Exécuter uniquement une suite de tests")
    args = parser.parse_args()

    results: list[TestResult] = []

    if args.only != "fields":
        print("\n▶  Suite : discover_model")
        print("─" * 40)
        for case in DISCOVER_CASES:
            r = run_discover_case(case, verbose=args.verbose)
            results.append(r)
            icon = "✅" if r.passed else "❌"
            print(f"  {icon}  {case.intent!r:40s}  {case.description}")

    if args.only != "discover":
        print("\n▶  Suite : get_model_fields")
        print("─" * 40)
        for case in FIELDS_CASES:
            r = run_fields_case(case, verbose=args.verbose)
            results.append(r)
            icon = "✅" if r.passed else "❌"
            print(f"  {icon}  {case.model:30s}  {case.description}")

    print_report(results)
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
