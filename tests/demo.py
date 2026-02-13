"""
Script de démonstration rapide du système de tests
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from test_router import RouterTest

def demo():
    """Démonstration rapide avec 3 questions"""
    print("\n" + "="*70)
    print("🎬 DÉMONSTRATION RAPIDE DU SYSTÈME DE TESTS")
    print("="*70 + "\n")
    
    print("Ce script va tester le Router avec 3 questions seulement.")
    print("Pour un benchmark complet, utilisez: python tests/benchmark.py\n")
    
    # Créer un mini-dataset
    mini_dataset = {
        "router_questions": [
            {
                "id": "demo_001",
                "question": "Combien de clients j'ai ?",
                "expected_route": "SQL"
            },
            {
                "id": "demo_002",
                "question": "Comment créer une facture ?",
                "expected_route": "RAG"
            },
            {
                "id": "demo_003",
                "question": "Liste mes 5 derniers produits",
                "expected_route": "SQL"
            }
        ]
    }
    
    # Sauvegarder temporairement
    import json
    temp_file = "tests/demo_dataset.json"
    with open(temp_file, 'w') as f:
        json.dump(mini_dataset, f)
    
    # Lancer le test
    tester = RouterTest(temp_file)
    report = tester.run_all_tests()
    
    # Nettoyer
    os.remove(temp_file)
    
    print("\n✨ Démonstration terminée !")
    print(f"📊 Précision: {report['summary']['accuracy']:.2f}%")
    print("\n💡 Pour tester SQL et RAG, lancez:")
    print("   python tests/test_sql_engine.py")
    print("   python tests/test_rag_engine.py")
    print("\n🚀 Pour le benchmark complet:")
    print("   python tests/benchmark.py\n")

if __name__ == "__main__":
    demo()
