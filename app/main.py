import sys
import os

# Imports des modules frères
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.router import route_question
from app.rag_engine import ask_odoo_rag
from app.sql_engine import ask_odoo_data

def main():
    print("="*60)
    print("🤖  ASSISTANT ODOO INTELLIGENT (Doc + Data)")
    print("    - Pose une question technique (ex: 'Comment confirmer une vente ?')")
    print("    - Pose une question sur tes données (ex: 'Combien de clients à Paris ?')")
    print("="*60)

    while True:
        try:
            user_input = input("\nToi : ")
            if user_input.lower() in ['q', 'quit', 'exit']:
                print("👋 Au revoir !")
                break
            
            # 1. Le Router décide
            intent = route_question(user_input)
            print(f"   [Analyse : Cette question concerne {intent}]")
            
            # 2. Aiguillage
            if intent == "SQL":
                response = ask_odoo_data(user_input)
            else:
                response = ask_odoo_rag(user_input)
            
            # 3. Réponse
            print(f"\n🤖 Assistant :\n{response}")
            
        except KeyboardInterrupt:
            print("\n👋 Arrêt forcé.")
            break
        except Exception as e:
            print(f"❌ Erreur inattendue : {e}")

if __name__ == "__main__":
    main()