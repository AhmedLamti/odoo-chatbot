"""
Tests du Router - Évaluation de la précision du routage
"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.router import route_question

class RouterTest:
    def __init__(self, test_datasets_path="tests/test_datasets.json"):
        """Initialise les tests avec le dataset"""
        with open(test_datasets_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.questions = data['router_questions']
        self.results = []
    
    def test_single_question(self, test_case):
        """Test une seule question de routage"""
        question = test_case['question']
        expected = test_case['expected_route']
        
        print(f"\n{'='*70}")
        print(f"🧪 Test: {test_case['id']}")
        print(f"   Question: {question}")
        print(f"   Route attendue: {expected}")
        print(f"{'='*70}")
        
        result = {
            'id': test_case['id'],
            'question': question,
            'expected_route': expected,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Mesure du temps de décision
            start = time.time()
            predicted = route_question(question)
            decision_time = time.time() - start
            
            result['predicted_route'] = predicted
            result['decision_time'] = round(decision_time, 2)
            
            # Vérification
            is_correct = (predicted == expected)
            result['is_correct'] = is_correct
            result['score'] = 1.0 if is_correct else 0.0
            result['status'] = "✅ CORRECT" if is_correct else "❌ INCORRECT"
            
            print(f"\n🎯 Route prédite: {predicted} ({decision_time:.2f}s)")
            print(f"   Résultat: {result['status']}")
            
        except Exception as e:
            result['status'] = "❌ ERROR"
            result['error'] = str(e)
            result['score'] = 0.0
            print(f"\n💥 Erreur: {e}")
        
        print(f"{'='*70}\n")
        return result
    
    def run_all_tests(self):
        """Lance tous les tests de routage"""
        print("\n" + "🚀 " * 30)
        print("DÉMARRAGE DES TESTS ROUTER")
        print("🚀 " * 30)
        
        for test_case in self.questions:
            result = self.test_single_question(test_case)
            self.results.append(result)
            time.sleep(0.5)  # Petite pause
        
        return self.generate_report()
    
    def generate_report(self):
        """Génère un rapport détaillé"""
        total = len(self.results)
        correct = sum(1 for r in self.results if r.get('is_correct', False))
        incorrect = total - correct
        
        accuracy = (correct / total * 100) if total > 0 else 0
        avg_time = sum(r.get('decision_time', 0) for r in self.results) / total
        
        # Analyse par type de route
        sql_predictions = [r for r in self.results if r.get('predicted_route') == 'SQL']
        rag_predictions = [r for r in self.results if r.get('predicted_route') == 'RAG']
        
        sql_accuracy = sum(1 for r in sql_predictions if r.get('is_correct', False)) / len(sql_predictions) * 100 if sql_predictions else 0
        rag_accuracy = sum(1 for r in rag_predictions if r.get('is_correct', False)) / len(rag_predictions) * 100 if rag_predictions else 0
        
        report = {
            'test_type': 'Router',
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total,
                'correct': correct,
                'incorrect': incorrect,
                'accuracy': round(accuracy, 2),
                'avg_decision_time': round(avg_time, 2),
                'sql_predictions': len(sql_predictions),
                'rag_predictions': len(rag_predictions),
                'sql_accuracy': round(sql_accuracy, 2),
                'rag_accuracy': round(rag_accuracy, 2)
            },
            'detailed_results': self.results
        }
        
        # Sauvegarde du rapport
        report_path = f"tests/results/router_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Affichage du résumé
        print("\n" + "="*70)
        print("📊 RAPPORT FINAL - ROUTER")
        print("="*70)
        print(f"Total de tests: {total}")
        print(f"✅ Corrects: {correct}")
        print(f"❌ Incorrects: {incorrect}")
        print(f"🎯 Précision globale: {accuracy:.2f}%")
        print(f"\n📊 Précision par route:")
        print(f"   SQL: {sql_accuracy:.2f}% ({len(sql_predictions)} prédictions)")
        print(f"   RAG: {rag_accuracy:.2f}% ({len(rag_predictions)} prédictions)")
        print(f"\n⏱️ Temps moyen de décision: {avg_time:.2f}s")
        print(f"\n💾 Rapport sauvegardé: {report_path}")
        print("="*70 + "\n")
        
        return report


if __name__ == "__main__":
    tester = RouterTest()
    tester.run_all_tests()
