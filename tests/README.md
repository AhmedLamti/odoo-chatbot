# 🧪 Tests & Benchmarks - Odoo Chatbot

Ce module contient l'infrastructure de tests pour évaluer les performances et la qualité des différents composants du chatbot.

## 📁 Structure

```
tests/
├── __init__.py
├── benchmark.py              # Orchestrateur principal
├── test_datasets.json        # Questions de test
├── test_router.py           # Tests du router
├── test_sql_engine.py       # Tests du moteur SQL
├── test_rag_engine.py       # Tests du moteur RAG
└── results/                 # Rapports générés (JSON)
```

## 🚀 Utilisation

### Lancer tous les tests

```bash
python tests/benchmark.py
```

### Lancer des tests spécifiques

```bash
# Router uniquement
python tests/benchmark.py --router-only

# Moteur SQL uniquement
python tests/benchmark.py --sql-only

# Moteur RAG uniquement
python tests/benchmark.py --rag-only

# Combinaisons personnalisées
python tests/benchmark.py --components router sql
```

### Lancer un composant individuellement

```bash
# Tester le router
python tests/test_router.py

# Tester le moteur SQL
python tests/test_sql_engine.py

# Tester le moteur RAG
python tests/test_rag_engine.py
```

## 📊 Métriques Évaluées

### Router
- ✅ **Précision** : Pourcentage de questions correctement routées
- ⏱️ **Temps de décision** : Temps moyen pour classifier une question

### Moteur SQL
- ✅ **Taux de réussite** : Pourcentage de requêtes exécutées avec succès
- 🎯 **Qualité SQL** : Correspondance au pattern SQL attendu
- ⏱️ **Temps de génération** : Temps pour générer la requête SQL
- ⏱️ **Temps d'exécution** : Temps d'exécution de la requête

### Moteur RAG
- ✅ **Taux de réussite** : Pourcentage de réponses de qualité
- 🎯 **Score qualité** : Basé sur la présence de mots-clés pertinents
- 🔍 **Pertinence documents** : Nombre de documents trouvés
- ⏱️ **Temps de recherche** : Temps de recherche vectorielle
- ⏱️ **Temps de génération** : Temps de génération de la réponse

## 📝 Dataset de Tests

Le fichier [test_datasets.json](test_datasets.json) contient :

- **8 questions SQL** (facile → difficile)
  - Comptages simples
  - Requêtes avec filtres
  - Jointures complexes
  - Agrégations

- **8 questions RAG** (documentation)
  - Questions techniques
  - Workflows
  - Configuration
  - Cas d'usage avancés

- **6 questions Router** (classification)
  - Mix SQL/RAG pour tester la précision

### Ajouter vos propres tests

Éditez `test_datasets.json` :

```json
{
  "sql_questions": [
    {
      "id": "sql_009",
      "question": "Votre question ici",
      "expected_sql_pattern": "Regex du SQL attendu",
      "expected_result_type": "count|list|sum|average",
      "category": "votre_categorie",
      "difficulty": "easy|medium|hard"
    }
  ]
}
```

## 📈 Rapports Générés

Les tests génèrent des rapports JSON dans `tests/results/` :

- `router_test_YYYYMMDD_HHMMSS.json`
- `sql_engine_test_YYYYMMDD_HHMMSS.json`
- `rag_engine_test_YYYYMMDD_HHMMSS.json`
- `benchmark_global_YYYYMMDD_HHMMSS.json` (consolidé)

### Structure d'un rapport

```json
{
  "test_type": "SQL Engine",
  "timestamp": "2026-02-13T10:30:00",
  "summary": {
    "total_tests": 8,
    "passed": 6,
    "partial": 1,
    "failed": 1,
    "success_rate": 75.0,
    "avg_generation_time": 3.45
  },
  "detailed_results": [...]
}
```

## 🎯 Exemple de Sortie

```
📊 RAPPORT FINAL - SQL ENGINE
======================================================================
Total de tests: 8
✅ Réussis: 6 (75.0%)
⚠️ Partiels: 1
❌ Échoués: 1

⏱️ Temps moyen de génération: 3.45s
⏱️ Temps moyen d'exécution: 0.12s

💾 Rapport sauvegardé: tests/results/sql_engine_test_20260213_103045.json
======================================================================
```

## 🔧 Personnalisation

### Modifier les seuils de score

Dans `test_rag_engine.py` :

```python
# Ligne ~120
if quality_score >= 0.7:      # Seuil PASS
    result['status'] = "✅ PASS"
elif quality_score >= 0.4:    # Seuil PARTIAL
    result['status'] = "⚠️ PARTIAL"
```

### Ajuster le nombre de documents RAG

Dans `test_rag_engine.py` :

```python
# Ligne ~70
docs = search_relevant_docs(question, limit=5)  # Modifier ici
```

### Changer les critères d'évaluation SQL

Dans `test_sql_engine.py` :

```python
# Méthode evaluate_sql_quality (ligne ~25)
# Modifier la logique de vérification du pattern
```

## 🐛 Dépannage

### "ModuleNotFoundError"
Assurez-vous d'exécuter depuis la racine du projet :
```bash
cd /home/ahmed/Documents/PFE/odoo_chatbot
python tests/benchmark.py
```

### Ollama trop lent
Réduisez le nombre de tests ou ajoutez des pauses :
```python
time.sleep(2)  # Augmenter la pause entre tests
```

### Base de données inaccessible
Vérifiez que PostgreSQL est démarré et que les credentials dans `config.py` sont corrects.

## 📊 Interprétation des Résultats

### Score Global
- **> 80%** : Excellent, le chatbot fonctionne très bien
- **60-80%** : Bon, quelques ajustements nécessaires
- **< 60%** : Améliorations requises (fine-tuning, prompts, données)

### Router
- Précision < 80% → Revoir les prompts de classification

### SQL
- Taux de réussite < 70% → Améliorer le schéma fourni au LLM
- Temps > 5s → Considérer un modèle plus léger

### RAG
- Qualité < 60% → Vérifier la qualité de la documentation indexée
- Temps > 8s → Réduire le nombre de documents ou optimiser les embeddings

## 🔮 Évolutions Futures

- [ ] Tests unitaires avec pytest
- [ ] Intégration continue (CI/CD)
- [ ] Comparaison de différents modèles LLM
- [ ] Tests de charge (latence sous pression)
- [ ] Métriques de coût (tokens consommés)
- [ ] Dashboard HTML interactif des résultats

---

💡 **Conseil** : Lancez un benchmark complet après chaque modification importante du code pour détecter les régressions.
