"""
Benchmark Global - Lance tous les tests et génère un rapport consolidé
"""
import sys
import os
import json
import argparse
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from test_router import RouterTest
from test_sql_engine import SQLEngineTest
from test_rag_engine import RAGEngineTest

class GlobalBenchmark:
    def __init__(self):
        self.reports = {}
        self.start_time = datetime.now()
    
    def run_router_tests(self):
        """Lance les tests du router"""
        print("\n" + "🎯"*30)
        print("PHASE 1/3 : TESTS ROUTER")
        print("🎯"*30 + "\n")
        tester = RouterTest()
        self.reports['router'] = tester.run_all_tests()
    
    def run_sql_tests(self):
        """Lance les tests SQL"""
        print("\n" + "🔧"*30)
        print("PHASE 2/3 : TESTS SQL ENGINE")
        print("🔧"*30 + "\n")
        tester = SQLEngineTest()
        self.reports['sql'] = tester.run_all_tests()
    
    def run_rag_tests(self):
        """Lance les tests RAG"""
        print("\n" + "📚"*30)
        print("PHASE 3/3 : TESTS RAG ENGINE")
        print("📚"*30 + "\n")
        tester = RAGEngineTest()
        self.reports['rag'] = tester.run_all_tests()
    
    def generate_consolidated_report(self):
        """Génère un rapport consolidé de tous les tests"""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # Calcul des métriques globales
        consolidated = {
            'test_suite': 'Odoo Chatbot - Benchmark Global',
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_duration_seconds': round(total_duration, 2),
            'components': {
                'router': self.reports.get('router', {}).get('summary', {}),
                'sql_engine': self.reports.get('sql', {}).get('summary', {}),
                'rag_engine': self.reports.get('rag', {}).get('summary', {})
            },
            'global_metrics': self._calculate_global_metrics()
        }
        
        # Sauvegarde
        report_path = f"tests/results/benchmark_global_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(consolidated, f, indent=2, ensure_ascii=False)
        
        # Affichage
        self._print_consolidated_report(consolidated, report_path)
        
        return consolidated
    
    def _calculate_global_metrics(self):
        """Calcule les métriques globales"""
        metrics = {}
        
        # Router
        router_summary = self.reports.get('router', {}).get('summary', {})
        metrics['router_accuracy'] = router_summary.get('accuracy', 0)
        
        # SQL
        sql_summary = self.reports.get('sql', {}).get('summary', {})
        metrics['sql_success_rate'] = sql_summary.get('success_rate', 0)
        metrics['sql_avg_time'] = sql_summary.get('avg_generation_time', 0)
        
        # RAG
        rag_summary = self.reports.get('rag', {}).get('summary', {})
        metrics['rag_success_rate'] = rag_summary.get('success_rate', 0)
        metrics['rag_avg_quality'] = rag_summary.get('avg_quality_score', 0)
        metrics['rag_avg_time'] = rag_summary.get('avg_total_time', 0)
        
        # Score global (moyenne pondérée)
        metrics['global_score'] = round(
            (metrics['router_accuracy'] * 0.2 + 
             metrics['sql_success_rate'] * 0.4 + 
             metrics['rag_success_rate'] * 0.4) / 100,
            2
        )
        
        return metrics
    
    def _print_consolidated_report(self, report, path):
        """Affiche le rapport consolidé de manière lisible"""
        print("\n" + "="*80)
        print("📊 RAPPORT CONSOLIDÉ - BENCHMARK GLOBAL")
        print("="*80)
        
        print(f"\n⏱️  Durée totale: {report['total_duration_seconds']:.2f}s")
        print(f"📅 Date: {report['end_time']}")
        
        metrics = report['global_metrics']
        
        print(f"\n{'='*80}")
        print("🎯 MÉTRIQUES GLOBALES")
        print(f"{'='*80}")
        print(f"Score Global: {metrics['global_score']}/1.0 ({metrics['global_score']*100:.1f}%)")
        
        print(f"\n📍 ROUTER")
        print(f"   Précision: {metrics['router_accuracy']:.2f}%")
        
        print(f"\n⚙️  SQL ENGINE")
        print(f"   Taux de réussite: {metrics['sql_success_rate']:.2f}%")
        print(f"   Temps moyen: {metrics['sql_avg_time']:.2f}s")
        
        print(f"\n📚 RAG ENGINE")
        print(f"   Taux de réussite: {metrics['rag_success_rate']:.2f}%")
        print(f"   Qualité moyenne: {metrics['rag_avg_quality']:.2f}/1.0")
        print(f"   Temps moyen: {metrics['rag_avg_time']:.2f}s")
        
        print(f"\n{'='*80}")
        print(f"💾 Rapport complet sauvegardé: {path}")
        print(f"{'='*80}\n")
    
    def run_full_benchmark(self, components=None):
        """
        Lance le benchmark complet ou seulement certains composants
        
        Args:
            components: Liste des composants à tester ['router', 'sql', 'rag']
                       Si None, lance tous les tests
        """
        if components is None:
            components = ['router', 'sql', 'rag']
        
        print("\n" + "🚀"*40)
        print("BENCHMARK GLOBAL - ODOO CHATBOT")
        print("🚀"*40)
        print(f"Composants à tester: {', '.join(components)}")
        print(f"Démarrage: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("🚀"*40 + "\n")
        
        if 'router' in components:
            self.run_router_tests()
        
        if 'sql' in components:
            self.run_sql_tests()
        
        if 'rag' in components:
            self.run_rag_tests()
        
        return self.generate_consolidated_report()


def main():
    """Point d'entrée avec arguments CLI"""
    parser = argparse.ArgumentParser(description='Benchmark du Chatbot Odoo')
    parser.add_argument(
        '--components',
        nargs='+',
        choices=['router', 'sql', 'rag'],
        help='Composants à tester (par défaut: tous)'
    )
    parser.add_argument(
        '--router-only',
        action='store_true',
        help='Tester uniquement le router'
    )
    parser.add_argument(
        '--sql-only',
        action='store_true',
        help='Tester uniquement le moteur SQL'
    )
    parser.add_argument(
        '--rag-only',
        action='store_true',
        help='Tester uniquement le moteur RAG'
    )
    
    args = parser.parse_args()
    
    # Déterminer les composants à tester
    components = None
    if args.router_only:
        components = ['router']
    elif args.sql_only:
        components = ['sql']
    elif args.rag_only:
        components = ['rag']
    elif args.components:
        components = args.components
    
    # Lancer le benchmark
    benchmark = GlobalBenchmark()
    benchmark.run_full_benchmark(components=components)


if __name__ == "__main__":
    main()
