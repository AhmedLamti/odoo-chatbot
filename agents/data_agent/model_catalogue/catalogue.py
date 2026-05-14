import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from config.settings import settings
from core.odoo_client import odoo_client

logger = logging.getLogger(__name__)

CATALOGUE_COLLECTION = "odoo_model_catalogue"
VECTOR_SIZE = 768

# --- NIVEAU 1 : Dictionnaire de synonymes métier ---
CORE_SYNONYMS = {
    # PRODUCTS
    "product.template": (
        "product catalog, main product, general article, product master, pricing, "
        "categories, how many products, count products, number of products, list products, "
        "product overview — NOT variants, NOT SKU, NOT color, NOT size"
    ),
    "product.product": (
        "variant only, specific SKU, color variant, size variant, attribute combination "
        "— NOT general product count, NOT product list"
    ),

    # SALES
    "sale.order": "sales order, quotation, sales confirmation, revenue per order, confirmed orders",
    "sale.order.line": "products inside a sales order, sold items, order lines, sale line details",

    # PURCHASE
    "purchase.order": "purchase order, supplier order, procurement, vendor order, pending purchases",
    "purchase.order.line": "items inside a purchase order, ordered articles, purchase line details, ordered products from supplier",

    # ACCOUNTING — les mal indexés
    "account.move": (
        "invoice, vendor bill, credit note, avoir client, avoir fournisseur, "
        "journal entry, ecriture comptable, accounting document, unpaid invoice, "
        "credit memo — NOT payment, NOT journal config"
    ),
    "account.payment": (
        "payment received, payment sent, bank payment, money received, money paid, "
        "paiement reçu, règlement, encaissement — NOT invoice, NOT bill"
    ),
    "account.tax": (
        "tax rate, VAT, TVA, taux TVA, taxe applicable, tax configuration, "
        "tax rules, taxe sur vente, taxe sur achat"
    ),
    "account.journal": "journal configuration, bank journal, sales journal, journal setup — NOT journal entries",
    "account.account": "chart of accounts, plan comptable, account code, account label, accounting account",
    "res.currency": "currency, exchange rate, taux de change, USD, EUR, devise",

    # HR — les mal indexés
    "hr.employee": "employee, staff, worker, headcount, nombre employés, liste employés, fiche employé",
    "hr.department": "department, service, organizational unit, liste départements",
    "hr.leave": (
        "leave request, time off, absence, vacation request, congé, "
        "congés en attente, sick day, leave validation, demande de congé"
    ),
    "hr.leave.allocation": (
        "leave allocation, vacation days balance, solde congés, "
        "days allocated, how many days off, quota congés"
    ),
    "hr.payslip": (
        "payslip, salary slip, pay stub, fiche de paie, bulletin de salaire, "
        "salary computation, pay january, paie mensuelle"
    ),
    "hr.payslip.run": "payslip batch, payroll run, batch paie, lot de bulletins",
    "hr.contract": "employment contract, wage, contrat de travail, contractual salary, salaire contractuel",

    # SHARED
    "res.partner": "customer, supplier, vendor, contact, client, company, person, address, fournisseur actif",
    "res.users": "system user, login, user account, utilisateur système, access rights",
}


class ModelCatalogue:
    def __init__(self):
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self._embed_model = None

    def _get_embed_model(self):
        if self._embed_model is None:
            from llama_index.embeddings.ollama import OllamaEmbedding
            self._embed_model = OllamaEmbedding(
                model_name=settings.ollama_embed_model,
                base_url=settings.ollama_base_url,
            )
        return self._embed_model

    def _embed(self, text: str) -> list[float]:
        return self._get_embed_model().get_text_embedding(text)

    # --- NIVEAU 2 : Nettoyage et Filtrage ---
    def _fetch_models(self) -> list[dict]:
        """Récupère les modèles en filtrant le bruit technique."""
        # On exclut les tables système qui polluent la recherche
        domain = [
            ('transient', '=', False),
            ('model', 'not ilike', 'ir.%'),
            ('model', 'not ilike', 'base.%'),
            ('model', 'not ilike', 'bus.%'),
            ('model', 'not ilike', 'web.%'),
        ]

        records = odoo_client.search_read(
            "ir.model", domain, ["model", "name"],
            limit=9999, order="model asc"
        )

        logger.info(f"[catalogue] {len(records)} modèles métiers conservés après filtrage.")

        formatted_models = []
        for r in records:
            model_tech_name = r["model"]
            friendly_name = r["name"]

            # Récupération des synonymes si existants
            syns = CORE_SYNONYMS.get(model_tech_name, "")

            # --- NIVEAU 1 : Signature d'embedding riche ---
            # On structure pour que le modèle 'voit' bien la différence entre nom technique et label
            rich_text = f"Odoo Model: {model_tech_name} | Label: {friendly_name}"
            if syns:
                rich_text += f" | Keywords: {syns}"

            formatted_models.append({
                "model": model_tech_name,
                "name": friendly_name,
                "embed_text": rich_text,
            })

        return formatted_models

    # (Le reste des méthodes build, search, etc. reste identique à ton code original)
    def _ensure_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if CATALOGUE_COLLECTION not in existing:
            self.client.create_collection(
                collection_name=CATALOGUE_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )

    def _drop_and_recreate(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if CATALOGUE_COLLECTION in existing:
            self.client.delete_collection(CATALOGUE_COLLECTION)
        self.client.create_collection(
            collection_name=CATALOGUE_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    def build(self):
        self._drop_and_recreate()
        models = self._fetch_models()
        points = []
        for m in models:
            vector = self._embed(m["embed_text"])
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"model": m["model"], "name": m["name"]},
            ))
            if len(points) >= 100:
                self.client.upsert(collection_name=CATALOGUE_COLLECTION, points=points)
                points = []
        if points:
            self.client.upsert(collection_name=CATALOGUE_COLLECTION, points=points)
        total = self.client.get_collection(CATALOGUE_COLLECTION).points_count
        logger.info(f"[catalogue] Build terminé — {total} modèles indexés")

    def search(self, query_en: str, top_k: int = 10) -> list[dict]:
        self._ensure_collection()
        vector = self._embed(query_en)
        results = self.client.query_points(
            collection_name=CATALOGUE_COLLECTION,
            query=vector,
            limit=top_k,
        ).points
        return [
            {"model": r.payload["model"], "name": r.payload["name"], "score": r.score}
            for r in results
        ]

    def count(self) -> int:
        self._ensure_collection()
        return self.client.get_collection(CATALOGUE_COLLECTION).points_count


model_catalogue = ModelCatalogue()
