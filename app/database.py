import psycopg2
from psycopg2.extras import RealDictCursor
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import DB_HOST, DB_NAME, DB_USER_RO, DB_PASS_RO, DB_USER_ADMIN, DB_PASS_ADMIN

def get_db_connection(admin=False):
    """
    Crée une connexion à la base de données.
    Si admin=True, utilise le compte admin (pour écrire).
    Si admin=False, utilise le compte lecture seule (pour le chatbot).
    """
    try:
        user = DB_USER_ADMIN if admin else DB_USER_RO
        password = DB_PASS_ADMIN if admin else DB_PASS_RO
        
        conn = psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=user,
            password=password
        )
        return conn
    except Exception as e:
        print(f"❌ Erreur critique de connexion DB : {e}")
        return None
    

def get_clean_odoo_schema():
    """
    Extrait le schéma des tables clés en filtrant agressivement le bruit technique.
    """
    # Liste des tables stratégiques
    target_tables = (
        'res_partner', 
        'product_template', 'product_product',
        'sale_order', 'sale_order_line', 
        'purchase_order', 'purchase_order_line',
        'stock_picking', 'stock_move', 'stock_quant',
        'account_move', 'account_move_line'
    )
    
    conn = get_db_connection(admin=False)
    if not conn:
        return "Erreur: Impossible de se connecter à la base pour lire le schéma."
        
    cursor = conn.cursor()
    
    schema_description = "Voici le schéma relationnel PostgreSQL d'Odoo :\n"
    
    print("--- EXTRACTION DU SCHÉMA ---")
    
    for table in target_tables:
        # On ajoute "AND table_schema = 'public'" pour être sûr
        cursor.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table}'
            AND table_schema = 'public'
            AND column_name NOT LIKE 'create_%%'
            AND column_name NOT LIKE 'write_%%'
            AND column_name NOT LIKE 'message_%%'
            AND column_name NOT LIKE 'activity_%%'
            AND column_name NOT LIKE 'website_%%'
            AND column_name NOT IN ('access_token', 'signup_token', 'password', 'image_1920', 'image_128')
            ORDER BY column_name;
        """)
        columns = cursor.fetchall()
        
        # DEBUG : Vérifie que sale_order est bien trouvé
        #print(f"✅ Table '{table}' : {len(columns)} colonnes trouvées.")
        
        if columns:
            schema_description += f"\nTABLE {table} (\n"
            for col, dtype in columns:
                # Simplification des types pour l'IA (character varying -> varchar)
                simple_type = dtype.replace("character varying", "varchar").replace("timestamp without time zone", "datetime")
                schema_description += f"  {col} {simple_type},\n"
            schema_description += ");\n"
        else:
            print(f"⚠️ ATTENTION : La table '{table}' semble vide ou inexistante !")
            
    conn.close()
    
    return schema_description