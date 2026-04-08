"""
Client XML-RPC Odoo — avec retry automatique
"""

import logging
import xmlrpc.client
from config.settings import settings
from utils.retry import with_retry

logger = logging.getLogger(__name__)


class OdooXMLRPC:
    def __init__(self):
        self.url = settings.odoo_url
        self.db = settings.odoo_db
        self.username = settings.odoo_username
        self.password = settings.odoo_password
        self._uid = None

    @with_retry(max_attempts=3, delay=1.0, backoff=2.0)
    def _get_uid(self) -> int:
        if self._uid is None:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            self._uid = common.authenticate(self.db, self.username, self.password, {})
            if not self._uid:
                raise ConnectionError(
                    f"Authentification Odoo échouée pour '{self.username}'"
                )
            logger.info(f"Odoo XML-RPC authentifié (uid={self._uid})")
        return self._uid

    def _models(self):
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    @with_retry(max_attempts=3, delay=1.0, backoff=2.0)
    def execute(self, model: str, method: str, *args, **kwargs) -> any:
        uid = self._get_uid()
        models = self._models()
        return models.execute_kw(
            self.db, uid, self.password, model, method, list(args), kwargs
        )

    # ── Commande de vente ─────────────────────────────────────────

    def create_sale_order(self, partner_name: str, products: list[dict]) -> dict:
        partner_ids = self.execute(
            "res.partner",
            "search",
            [["name", "ilike", partner_name], ["customer_rank", ">", 0]],
        )
        if not partner_ids:
            return {"success": False, "error": f"Client '{partner_name}' introuvable"}
        return self.create_sale_order_by_id(partner_ids[0], products)

    def create_sale_order_by_id(self, partner_id: int, products: list[dict]) -> dict:
        order_lines = []
        for p in products:
            product_id = p.get("product_id")
            if not product_id:
                product_ids = self.execute(
                    "product.product", "search", [["name", "ilike", p["name"]]]
                )
                if not product_ids:
                    return {
                        "success": False,
                        "error": f"Produit '{p['name']}' introuvable",
                    }
                product_id = product_ids[0]
            order_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": product_id,
                        "product_uom_qty": p.get("qty", 1),
                        "price_unit": p.get("price", 0),
                    },
                )
            )

        order_id = self.execute(
            "sale.order",
            "create",
            {
                "partner_id": partner_id,
                "order_line": order_lines,
            },
        )
        order = self.execute(
            "sale.order", "read", [order_id], fields=["name", "amount_total", "state"]
        )[0]
        return {
            "success": True,
            "order_id": order_id,
            "order_name": order["name"],
            "amount_total": order["amount_total"],
            "message": f"Commande {order['name']} créée avec succès (total: {order['amount_total']} €)",
        }

    def confirm_sale_order(self, order_name: str) -> dict:
        order_ids = self.execute(
            "sale.order", "search", [["name", "ilike", order_name]]
        )
        if not order_ids:
            return {"success": False, "error": f"Commande '{order_name}' introuvable"}
        self.execute("sale.order", "action_confirm", [order_ids[0]])
        return {
            "success": True,
            "message": f"Commande '{order_name}' confirmée avec succès",
        }

    # ── Facture ───────────────────────────────────────────────────

    def create_invoice(self, partner_name: str, lines: list[dict]) -> dict:
        partner_ids = self.execute(
            "res.partner",
            "search",
            [["name", "ilike", partner_name], ["customer_rank", ">", 0]],
        )
        if not partner_ids:
            return {"success": False, "error": f"Client '{partner_name}' introuvable"}
        return self.create_invoice_by_id(partner_ids[0], lines)

    def create_invoice_by_id(self, partner_id: int, lines: list[dict]) -> dict:
        invoice_lines = [
            (
                0,
                0,
                {
                    "name": l.get("name", "Service"),
                    "quantity": l.get("qty", 1),
                    "price_unit": l.get("price", 0),
                },
            )
            for l in lines
        ]

        invoice_id = self.execute(
            "account.move",
            "create",
            {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "invoice_line_ids": invoice_lines,
            },
        )
        invoice = self.execute(
            "account.move",
            "read",
            [invoice_id],
            fields=["name", "amount_total", "state"],
        )[0]
        return {
            "success": True,
            "invoice_id": invoice_id,
            "invoice_name": invoice["name"],
            "amount_total": invoice["amount_total"],
            "message": f"Facture {invoice['name']} créée (total: {invoice['amount_total']} €)",
        }

    def validate_invoice(self, invoice_name: str) -> dict:
        invoice_ids = self.execute(
            "account.move",
            "search",
            [["name", "ilike", invoice_name], ["move_type", "=", "out_invoice"]],
        )
        if not invoice_ids:
            return {"success": False, "error": f"Facture '{invoice_name}' introuvable"}
        self.execute("account.move", "action_post", [invoice_ids[0]])
        return {
            "success": True,
            "message": f"Facture '{invoice_name}' validée avec succès",
        }

    # ── Employé ───────────────────────────────────────────────────

    def create_employee(
        self,
        name: str,
        job_title: str = "",
        department_id: int = None,
        department_name: str = "",
    ) -> dict:
        vals = {"name": name}
        if job_title:
            vals["job_title"] = job_title
        if department_id:
            vals["department_id"] = department_id
        elif department_name:
            dept_ids = self.execute(
                "hr.department", "search", [["name", "ilike", department_name]]
            )
            if dept_ids:
                vals["department_id"] = dept_ids[0]
            else:
                return {
                    "success": False,
                    "error": f"Département '{department_name}' introuvable",
                }
        employee_id = self.execute("hr.employee", "create", vals)
        return {
            "success": True,
            "employee_id": employee_id,
            "message": f"Employé '{name}' créé avec succès"
            + (f" dans le département '{department_name}'" if department_name else ""),
        }

    # ── Produit / Stock ───────────────────────────────────────────

    def update_product_price(self, product_name: str, new_price: float) -> dict:
        product_ids = self.execute(
            "product.template", "search", [["name", "ilike", product_name]]
        )
        if not product_ids:
            return {"success": False, "error": f"Produit '{product_name}' introuvable"}
        return self.update_product_price_by_id(product_ids[0], new_price, product_name)

    def update_product_price_by_id(
        self, product_id: int, new_price: float, product_name: str = ""
    ) -> dict:
        self.execute(
            "product.template", "write", [product_id], {"list_price": new_price}
        )
        return {
            "success": True,
            "message": f"Prix de '{product_name}' mis à jour à {new_price} €",
        }

    def update_product_stock(
        self, product_name: str, quantity: float, location: str = "WH/Stock"
    ) -> dict:
        product_ids = self.execute(
            "product.product", "search", [["name", "ilike", product_name]]
        )
        if not product_ids:
            return {"success": False, "error": f"Produit '{product_name}' introuvable"}
        return self.update_product_stock_by_id(product_ids[0], quantity, product_name)

    def update_product_stock_by_id(
        self,
        product_id: int,
        quantity: float,
        product_name: str = "",
        location: str = "WH/Stock",
    ) -> dict:
        location_ids = self.execute(
            "stock.location",
            "search",
            [["complete_name", "ilike", location], ["usage", "=", "internal"]],
        )
        if not location_ids:
            return {"success": False, "error": f"Emplacement '{location}' introuvable"}
        quant_id = self.execute(
            "stock.quant",
            "create",
            {
                "product_id": product_id,
                "location_id": location_ids[0],
                "inventory_quantity": quantity,
            },
        )
        self.execute("stock.quant", "action_apply_inventory", [quant_id])
        return {
            "success": True,
            "message": f"Stock de '{product_name}' ajusté à {quantity} unités",
        }

    # ── Email ─────────────────────────────────────────────────────

    def send_email(self, partner_name: str, subject: str, body: str) -> dict:
        partner_ids = self.execute(
            "res.partner", "search", [["name", "ilike", partner_name]]
        )
        if not partner_ids:
            return {"success": False, "error": f"Contact '{partner_name}' introuvable"}
        partner = self.execute(
            "res.partner", "read", [partner_ids[0]], fields=["email", "name"]
        )[0]
        if not partner.get("email"):
            return {
                "success": False,
                "error": f"'{partner_name}' n'a pas d'adresse email",
            }
        mail_id = self.execute(
            "mail.mail",
            "create",
            {
                "subject": subject,
                "body_html": f"<p>{body}</p>",
                "email_to": partner["email"],
            },
        )
        self.execute("mail.mail", "send", [mail_id])
        return {
            "success": True,
            "message": f"Email envoyé à '{partner['name']}' ({partner['email']}) — Sujet: {subject}",
        }
