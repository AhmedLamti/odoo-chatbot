from agents.data_agent.agent import run_data_agent

questions = [
    # ── Basiques ──────────────────────────────────────────────
    "Combien de clients avons-nous ?",
    "Combien de fournisseurs avons-nous ?",
    "Combien d'employés avons-nous ?",
    "Combien de produits avons-nous ?",

    # # ── Ventes ────────────────────────────────────────────────
    # "Quel est le chiffre d'affaires total ?",
    # "Liste des 5 meilleures commandes",
    # "Quels sont les meilleurs clients par chiffre d'affaires ?",
    # "Ventes par commercial",
    #
    # # ── Facturation ───────────────────────────────────────────
    # "Liste des factures impayées",
    # "Quel est le montant total des factures validées ?",
    #
    # # ── Stock ─────────────────────────────────────────────────
    # "Quel est le stock disponible par produit ?",
    #
    # # ── RH ────────────────────────────────────────────────────
    # "Liste des employés par département",
    # "Combien d'employés dans le département Sales ?",
    #
    # # ── Achats ────────────────────────────────────────────────
    # "Liste des commandes d'achat confirmées",
    # "Quels sont les meilleurs fournisseurs par montant d'achat ?",

    # ── Graphiques ────────────────────────────────────────────
    # "Graphique des ventes par date",
    # "Graphique des employés par département",
    # "Graphique des factures impayées par client",
]

if __name__ == "__main__":
    passed = 0
    failed = 0

    for i, q in enumerate(questions):
        print(f"\n{'=' * 50}")
        print(f"Q: {q}")
        try:
            r = run_data_agent(q, thread_id=f"test_{i}")
            print(f"R: {r['answer']}")
            passed += 1
        except Exception as e:
            print(f"ERREUR: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Résultats: {passed}/{len(questions)} réussis — {failed} échecs")
