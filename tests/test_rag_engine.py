"""
Tests du moteur RAG - Évaluation de la qualité et des performances
"""
import sys
import os
import json
import time
import re
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.rag_engine import ask_odoo_rag, search_relevant_docs

class RAGEngineTest:
    def __init__(self, test_datasets_path="tests/test_datasets.json"):
        """Initialise les tests avec le dataset"""
        with open(test_datasets_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.questions = data['rag_questions']
        self.results = []
    
    def evaluate_response_quality(self, response, keywords):
        """
        Évalue la qualité de la réponse basée sur la présence de mots-clés
        Returns: (score, details)
        """
        response_lower = response.lower()
        
        # Vérifications
        found_keywords = [kw for kw in keywords if kw.lower() in response_lower]
        keyword_score = len(found_keywords) / len(keywords)
        
        # Vérifier la longueur (réponse trop courte = probablement incomplète)
        length_score = 1.0 if len(response) > 100 else 0.5
        
        # Vérifier qu'il n'y a pas de message d'erreur
        has_error = any(err in response_lower for err in ["erreur", "error", "impossible", "aucun document"])
        error_penalty = 0.0 if has_error else 1.0
        
        # Score global
        final_score = (keyword_score * 0.6 + length_score * 0.2 + error_penalty * 0.2)
        
        details = {
            'found_keywords': found_keywords,
            'keyword_coverage': f"{len(found_keywords)}/{len(keywords)}",
            'response_length': len(response),
            'has_error': has_error
        }
        
        return round(final_score, 2), details
    
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
            # 1. Mesure du temps de recherche de documents
            start_search = time.time()
            docs = search_relevant_docs(question, limit=5)
            search_time = time.time() - start_search
            
            result['search_time'] = round(search_time, 2)
            result['docs_found'] = len(docs)
            
            print(f"\n🔍 Recherche ({search_time:.2f}s): {len(docs)} documents trouvés")
            
            if docs:
                print(f"   Top 3 sources:")
                for i, doc in enumerate(docs[:3]):
                    print(f"   {i+1}. {doc.get('source', 'N/A')}")
            
            # 2. Génération de la réponse complète
            start_gen = time.time()
            response = ask_odoo_rag(question)
            gen_time = time.time() - start_gen
            
            result['generation_time'] = round(gen_time, 2)
            result['total_time'] = round(search_time + gen_time, 2)
            result['response'] = response
            
            print(f"\n💬 Réponse générée ({gen_time:.2f}s):")
            print(f"   {response[:200]}..." if len(response) > 200 else f"   {response}")
            
            # 3. Évaluation de la qualité
            quality_score, quality_details = self.evaluate_response_quality(
                response,
                test_case['keywords']
            )
            
            result['quality_score'] = quality_score
            result['quality_details'] = quality_details
            
            print(f"\n🎯 Évaluation de la qualité:")
            print(f"   Score: {quality_score}/1.0")
            print(f"   Mots-clés trouvés: {quality_details['keyword_coverage']}")
            print(f"   Longueur réponse: {quality_details['response_length']} caractères")
            print(f"   Erreur détectée: {'Oui' if quality_details['has_error'] else 'Non'}")
            
            # 4. Détermination du statut
            if quality_score >= 0.7:
                result['status'] = "✅ PASS"
            elif quality_score >= 0.4:
                result['status'] = "⚠️ PARTIAL"
            else:
                result['status'] = "❌ FAIL"
            
            result['overall_score'] = quality_score
            
        except Exception as e:
            result['status'] = "❌ ERROR"
            result['error'] = str(e)
            result['overall_score'] = 0.0
            print(f"\n💥 Erreur inattendue: {e}")
        
        print(f"\n{'='*70}")
        print(f"Résultat: {result['status']} | Score: {result.get('overall_score', 0)}/1.0")
        print(f"{'='*70}\n")
        
        return result
    
    def run_all_tests(self):
        """Lance tous les tests RAG"""
        print("\n" + "🚀 " * 30)
        print("DÉMARRAGE DES TESTS RAG ENGINE")
        print("🚀 " * 30)
        
        for test_case in self.questions:
            result = self.test_single_question(test_case)
            self.results.append(result)
            time.sleep(1)  # Pause entre les tests
        
        return self.generate_report()
    
    def generate_report(self):
        """Génère un rapport détaillé"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.get('overall_score', 0) >= 0.7)
        partial = sum(1 for r in self.results if 0.4 <= r.get('overall_score', 0) < 0.7)
        failed = sum(1 for r in self.results if r.get('overall_score', 0) < 0.4)
        
        avg_search_time = sum(r.get('search_time', 0) for r in self.results) / total
        avg_gen_time = sum(r.get('generation_time', 0) for r in self.results) / total
        avg_total_time = sum(r.get('total_time', 0) for r in self.results) / total
        avg_quality = sum(r.get('overall_score', 0) for r in self.results) / total
        
        report = {
            'test_type': 'RAG Engine',
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total,
                'passed': passed,
                'partial': partial,
                'failed': failed,
                'success_rate': round((passed / total) * 100, 2) if total > 0 else 0,
                'avg_quality_score': round(avg_quality, 2),
                'avg_search_time': round(avg_search_time, 2),
                'avg_generation_time': round(avg_gen_time, 2),
                'avg_total_time': round(avg_total_time, 2)
            },
            'detailed_results': self.results
        }
        
        # Sauvegarde du rapport
        report_path = f"tests/results/rag_engine_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Affichage du résumé
        print("\n" + "="*70)
        print("📊 RAPPORT FINAL - RAG ENGINE")
        print("="*70)
        print(f"Total de tests: {total}")
        print(f"✅ Réussis: {passed} ({report['summary']['success_rate']}%)")
        print(f"⚠️ Partiels: {partial}")
        print(f"❌ Échoués: {failed}")
        print(f"\n🎯 Score qualité moyen: {avg_quality:.2f}/1.0")
        print(f"\n⏱️ Temps moyen de recherche: {avg_search_time:.2f}s")
        print(f"⏱️ Temps moyen de génération: {avg_gen_time:.2f}s")
        print(f"⏱️ Temps total moyen: {avg_total_time:.2f}s")
        print(f"\n💾 Rapport sauvegardé: {report_path}")
        print("="*70 + "\n")
        
        return report


if __name__ == "__main__":
    tester = RAGEngineTest()
    tester.run_all_tests()
