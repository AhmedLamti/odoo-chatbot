"""
Tests du moteur SQL - Évaluation de la qualité et des performances
"""
import sys
import os
import json
import time
import re
from datetime import datetime

# Configuration des imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.sql_engine import generate_sql_query, execute_sql_query, ask_odoo_data

class SQLEngineTest:
    def __init__(self, test_datasets_path="tests/test_datasets.json"):
        """Initialise les tests avec le dataset"""
        with open(test_datasets_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.questions = data['sql_questions']
        self.results = []
        
    def evaluate_sql_quality(self, generated_sql, expected_pattern):
        """
        Évalue si le SQL généré correspond au pattern attendu
        Returns: (score, details)
        """
        # Normalisation
        sql_normalized = re.sub(r'\s+', ' ', generated_sql.lower().strip())
        pattern_normalized = expected_pattern.lower()
        
        # Vérification du pattern (regex)
        if re.search(pattern_normalized, sql_normalized, re.IGNORECASE):
            return 1.0, "✓ Pattern SQL correct"
        else:
            return 0.0, "✗ Pattern SQL incorrect"
    
    def test_single_question(self, test_case):
        """Test une seule question"""
        question = test_case['question']
        print(f"\n{'='*70}")
        print(f"🧪 Test: {test_case['id']} - {question}")
        print(f"   Catégorie: {test_case['category']} | Difficulté: {test_case['difficulty']}")
        print(f"{'='*70}")
        
        result = {
            'id': test_case['id'],
            'question': question,
            'category': test_case['category'],
            'difficulty': test_case['difficulty'],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # 1. Mesure du temps de génération SQL
            start_gen = time.time()
            generated_sql = generate_sql_query(question)
            gen_time = time.time() - start_gen
            
            result['generated_sql'] = generated_sql
            result['generation_time'] = round(gen_time, 2)
            
            print(f"\n📝 SQL Généré ({gen_time:.2f}s):")
            print(f"   {generated_sql}")
            
            # 2. Évaluation de la qualité du SQL
            quality_score, quality_msg = self.evaluate_sql_quality(
                generated_sql, 
                test_case['expected_sql_pattern']
            )
            result['quality_score'] = quality_score
            result['quality_message'] = quality_msg
            
            print(f"\n🎯 Qualité SQL: {quality_msg} (Score: {quality_score})")
            
            # 3. Tentative d'exécution
            start_exec = time.time()
            exec_result, columns = execute_sql_query(generated_sql)
            exec_time = time.time() - start_exec
            
            result['execution_time'] = round(exec_time, 2)
            
            # 4. Vérification du résultat
            if isinstance(exec_result, str) and "Erreur" in exec_result:
                result['execution_success'] = False
                result['error'] = exec_result
                print(f"\n❌ Exécution échouée: {exec_result}")
            else:
                result['execution_success'] = True
                result['row_count'] = len(exec_result)
                result['columns'] = columns
                print(f"\n✅ Exécution réussie ({exec_time:.2f}s)")
                print(f"   Rows: {len(exec_result)} | Columns: {columns}")
                
                # Afficher un échantillon des résultats
                if exec_result:
                    print(f"\n📊 Échantillon des résultats:")
                    for i, row in enumerate(exec_result[:3]):
                        print(f"   {i+1}. {row}")
            
            # 5. Score global
            if result['execution_success'] and quality_score > 0:
                result['overall_score'] = 1.0
                result['status'] = "✅ PASS"
            elif result['execution_success']:
                result['overall_score'] = 0.5
                result['status'] = "⚠️ PARTIAL"
            else:
                result['overall_score'] = 0.0
                result['status'] = "❌ FAIL"
                
        except Exception as e:
            result['status'] = "❌ ERROR"
            result['error'] = str(e)
            result['overall_score'] = 0.0
            print(f"\n💥 Erreur inattendue: {e}")
        
        print(f"\n{'='*70}")
        print(f"Résultat: {result['status']} | Score: {result.get('overall_score', 0)}")
        print(f"{'='*70}\n")
        
        return result
    
    def run_all_tests(self):
        """Lance tous les tests SQL"""
        print("\n" + "🚀 " * 30)
        print("DÉMARRAGE DES TESTS SQL ENGINE")
        print("🚀 " * 30)
        
        for test_case in self.questions:
            result = self.test_single_question(test_case)
            self.results.append(result)
            time.sleep(1)  # Pause entre les tests pour ne pas surcharger Ollama
        
        return self.generate_report()
    
    def generate_report(self):
        """Génère un rapport détaillé"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get('overall_score', 0) == 1.0)
        partial = sum(1 for r in self.results if r.get('overall_score', 0) == 0.5)
        failed = sum(1 for r in self.results if r.get('overall_score', 0) == 0.0)
        
        avg_gen_time = sum(r.get('generation_time', 0) for r in self.results) / total
        avg_exec_time = sum(r.get('execution_time', 0) for r in self.results if 'execution_time' in r) / max(1, sum(1 for r in self.results if 'execution_time' in r))
        
        report = {
            'test_type': 'SQL Engine',
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total,
                'passed': passed,
                'partial': partial,
                'failed': failed,
                'success_rate': round((passed / total) * 100, 2) if total > 0 else 0,
                'avg_generation_time': round(avg_gen_time, 2),
                'avg_execution_time': round(avg_exec_time, 2)
            },
            'detailed_results': self.results
        }
        
        # Sauvegarde du rapport
        report_path = f"tests/results/sql_engine_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Affichage du résumé
        print("\n" + "="*70)
        print("📊 RAPPORT FINAL - SQL ENGINE")
        print("="*70)
        print(f"Total de tests: {total}")
        print(f"✅ Réussis: {passed} ({report['summary']['success_rate']}%)")
        print(f"⚠️ Partiels: {partial}")
        print(f"❌ Échoués: {failed}")
        print(f"\n⏱️ Temps moyen de génération: {avg_gen_time:.2f}s")
        print(f"⏱️ Temps moyen d'exécution: {avg_exec_time:.2f}s")
        print(f"\n💾 Rapport sauvegardé: {report_path}")
        print("="*70 + "\n")
        
        return report


if __name__ == "__main__":
    tester = SQLEngineTest()
    tester.run_all_tests()
