import ollama
import sys
import os
import re

# --- IMPORTS ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.database import get_clean_odoo_schema, get_db_connection
from config import LLM_MODEL, LLM_MODEL_SQL

# --- SCHÉMA SIMPLIFIÉ ODOO ---
ODOO_SCHEMA = get_clean_odoo_schema()

def extract_sql_code(text: str):
    # Supprime les balises markdown
    text = re.sub(r"```sql|```", "", text)
    # Cherche le premier SELECT et prend tout jusqu'au point-virgule ou la fin
    match = re.search(r"(SELECT.*)", text, re.IGNORECASE | re.DOTALL)
    if match:
        sql = match.group(1).split(';')[0]
        return sql.strip()
    return text.strip()

def generate_sql_query(question: str):
    """
    Génération SQL Générique et Robuste.
    """
    
    # --- PROMPT GÉNÉRIQUE ---
    # On donne au modèle la "logique métier" d'Odoo pour qu'il comprenne n'importe quelle question.
    prompt = f"""
        ### Task
        Generate a PostgreSQL query to answer the following question:
        {question}

        ### Database Schema
        {ODOO_SCHEMA}

        ### Odoo Specific Rules (Strict)
        1. **Clients**: Use table `res_partner`. A partner is a client if `customer_rank > 0` OR `is_company = true`.
        2. **Column Names**: ONLY use columns listed in the schema above. Do not invent columns like 'payment_date'.
        3. **Simple Count**: If the question asks "How many", use `SELECT COUNT(*) FROM table`. Do not join `account_move` unless specifically asked about invoices.
        4. **Joins**: Only use JOIN if the data is in two different tables.

        ### Response Format
        Return ONLY the SQL query code. No comments, no explanations.
        Start directly with SELECT.

        ### SQL Query
        """
    
    print(f"🤔 Génération du SQL ({LLM_MODEL_SQL}) pour : '{question}'...")
    
    # Appel au modèle
    response = ollama.chat(model=LLM_MODEL_SQL, messages=[{'role': 'user', 'content': prompt}])
    
    raw_response = response['message']['content']
    print(f"📝 Réponse brute : {raw_response}")
    
    # --- NETTOYAGE ---
    clean_sql = extract_sql_code(raw_response)
    
    # Reconstruction de la requête complète
    # Si le modèle a omis le SELECT initial (fréquent avec ce prompt), on l'ajoute.
    if not clean_sql.lower().startswith("select"):
        final_sql = "SELECT " + clean_sql
    else:
        final_sql = clean_sql
        
    return final_sql

def execute_sql_query(sql: str):
    """
    Exécution sécurisée.
    """
    if not sql or len(sql) < 10:
        return "❌ Erreur : SQL vide.", []

    conn = get_db_connection(admin=False)
    if not conn:
        return "❌ Erreur de connexion DB.", []
    
    cursor = conn.cursor()
    try:
        print(f"⚡ Exécution SQL : {sql}")
        cursor.execute(sql)
        results = cursor.fetchall()
        
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
        conn.close()
        return results, columns

    except Exception as e:
        conn.close()
        return f"❌ Erreur SQL : {e}", []

def ask_odoo_data(question: str):
    # 1. Génération
    sql = generate_sql_query(question)
    
    # 2. Exécution
    results, columns = execute_sql_query(sql)
    
    # 3. Gestion Erreurs
    if isinstance(results, str) and results.startswith("❌"):
        return results
    
    if not results:
        return "Je n'ai trouvé aucun résultat correspondant."

    # 4. Synthèse (Modèle Chat)
    summary_prompt = f"""
    Tu es un assistant Odoo.
    
    Question utilisateur : "{question}"
    Résultat Base de Données : {results}
    Colonnes : {columns}
    
    Instructions :
    - Réponds naturellement en français.
    - Si le résultat est un nombre unique, donne-le simplement.
    - Si c'est une liste, cite les éléments principaux.
    - Ne parle pas technique (pas de "tuple", "ID", "SQL").
    """
    
    print("💬 Synthèse de la réponse...")
    response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': summary_prompt}])
    
    return response['message']['content']

if __name__ == "__main__":
    #print(ODOO_SCHEMA)
    # Test avec une question différente pour vérifier la généricité
    #print(ask_odoo_data("Combien j'ai de clients ?"))
    print(ask_odoo_data("Liste moi 5 produits"))