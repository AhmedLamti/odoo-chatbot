import logging
import xmlrpc.client

from config.settings import settings
from utils.retry import with_retry

logger = logging.getLogger(__name__)


class OdooClient:
    """
    Client XML-RPC Odoo partagé — authentification par API Key
    """

    def __init__(self):
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.username = settings.odoo_username
        self.api_key = settings.odoo_api_key
        self._uid = None

    @with_retry(max_attempts=3, delay=1.0, backoff=2.0)
    def _get_uid(self) -> int:
        if self._uid is None:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            self._uid = common.authenticate(
                self.db, self.username, self.api_key, {}
            )
            if not self._uid:
                raise ConnectionError(
                    f"Authentification Odoo échouée pour '{self.username}'"
                )
            logger.info(f"Odoo authentifié via API Key (uid={self._uid})")
        return self._uid

    def _models(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    @with_retry(max_attempts=3, delay=1.0, backoff=2.0)
    def execute(self, model: str, method: str, *args, **kwargs):
        uid = self._get_uid()
        return self._models().execute_kw(
            self.db, uid, self.api_key,
            model, method, list(args), kwargs
        )

    def _clean_domain(self, domain: list) -> list:
        """
        Remplace None par False pour la compatibilité XML-RPC.
        Les opérateurs logiques Odoo ("|", "&", "!") sont des strings
        simples — ils ne doivent pas être dépaquetés en (f, op, v).
        """
        if not domain:
            return []
        cleaned = []
        for item in domain:
            if isinstance(item, str):  # opérateur logique "|", "&", "!"
                cleaned.append(item)
            else:
                f, op, v = item
                cleaned.append([f, op, False if v is None else v])
        return cleaned

    def search_read(self, model: str, domain: list,
                    fields: list, limit: int = 80,
                    order: str = "") -> list:
        kwargs = {"fields": fields, "limit": limit}
        if order:
            kwargs["order"] = order
        return self.execute(model, "search_read", self._clean_domain(domain), **kwargs)

    def search_count(self, model: str, domain: list) -> int:
        return self.execute(model, "search_count", self._clean_domain(domain))

    def read_group(self, model: str, domain: list,
                   fields: list, groupby: list,
                   limit: int = 80, orderby: str = "") -> list:
        """
        GROUP BY cote Odoo — agrégats calcules directement par le serveur.
        Evite tout calcul manuel cote Python ou LLM.
        """
        kwargs = {"lazy": False}
        if limit:
            kwargs["limit"] = limit
        if orderby:
            kwargs["orderby"] = orderby
        return self.execute(
            model, "read_group",
            self._clean_domain(domain), fields, groupby,
            **kwargs
        )

    def fields_get(self, model: str) -> dict:
        EXCLUDED_TYPES = ["binary", "html", "serialized"]
        EXCLUDED_PREFIXES = ["message_", "activity_", "website_"]
        fields = self.execute(
            model, "fields_get", [],
            {"attributes": ["string", "type"]}
        )
        return {
            k: v for k, v in fields.items()
            if v.get("type") not in EXCLUDED_TYPES
               and not any(k.startswith(p) for p in EXCLUDED_PREFIXES)
        }


odoo_client = OdooClient()
