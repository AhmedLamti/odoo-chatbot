import json
import xmlrpc.client

# Configuration Odoo
URL = 'http://localhost:8071'
DB = 'Community16'
USER = 'admin'
PASSWORD = 'admin'


def get_odoo_schema():
    # Connexion
    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(URL))
    uid = common.authenticate(DB, USER, PASSWORD, {})
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(URL))

    print("Extraction des modèles en cours...")

    # 1. Récupérer tous les modèles
    model_records = models.execute_kw(DB, uid, PASSWORD,
                                      'ir.model', 'search_read',
                                      [[('transient', '=', False)]],
                                      {'fields': ['id', 'model', 'name']}
                                      )

    schema = {}
    print(f"{len(model_records)} modèles trouvés. Extraction des champs...")

    # 2. Récupérer tous les champs
    # CORRECTION ICI : on demande 'model' au lieu de 'model_id'
    field_records = models.execute_kw(DB, uid, PASSWORD,
                                      'ir.model.fields', 'search_read',
                                      [[]],
                                      {'fields': ['model', 'name', 'field_description', 'ttype', 'relation']}
                                      )

    # 3. Structurer les données
    for model in model_records:
        schema[model['model']] = {
            "description": model['name'],
            "fields": {}
        }

    # 4. Remplir les champs
    for field in field_records:
        # CORRECTION ICI : on utilise directement la valeur textuelle du champ 'model'
        model_technical_name = field.get('model')

        if model_technical_name and model_technical_name in schema:
            schema[model_technical_name]["fields"][field['name']] = {
                "type": field['ttype'],
                "description": field['field_description']
            }
            # Si c'est un champ relationnel, on ajoute le modèle cible
            if field.get('relation'):
                schema[model_technical_name]["fields"][field['name']]["related_model"] = field['relation']

    # 5. Sauvegarder en JSON
    with open('schema_odoo.json', 'w', encoding='utf-8') as f:
        json.dump(schema, f, ensure_ascii=False, indent=4)

    print("Extraction terminée ! Fichier sauvegardé sous 'schema_odoo.json'")


if __name__ == "__main__":
    get_odoo_schema()
