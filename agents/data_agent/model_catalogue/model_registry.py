"""
Static registry of Odoo models covered by the SQL agent.

Modules in scope:
  - Produits (product)
  - Ventes (sale)
  - Achats (purchase)
  - Facturation / Comptabilité (account)
  - Employés (hr)
  - Projet & Tâches (project)
  - Congés (hr.leave)
  - Contacts (res.partner)

Each entry:
  "technical.model.name": {
      "name": "<human label>",
      "description": "<what this model stores and when to use it>",
  }
"""

MODEL_REGISTRY: dict[str, dict[str, str]] = {

    # ─────────────────────────────────────────
    # PRODUITS
    # ─────────────────────────────────────────
    "product.template": {
        "name": "Product Template",
        "description": (
            "Represents the general product definition: name, category, price, description. "
            "Use for: counting products, listing the product catalog, product pricing, "
            "products by category, checking if a product exists, product overview. "
            "This is the right model whenever the question is about products in general. "
            "Do NOT use when the question targets a specific variant (color, size, attribute). "
            "Examples: 'how many products', 'list all products', 'product price', "
            "'products in category X'."
        ),
    },
    "product.product": {
        "name": "Product Variant",
        "description": (
            "Represents a specific product variant — a unique combination of attributes "
            "such as color, size, or material (e.g. T-shirt / Blue / XL). "
            "Use ONLY when the question explicitly targets a variant, a specific SKU, "
            "or a specific attribute combination. "
            "Do NOT use for general product questions — use product.template instead. "
            "Examples: 'blue variant of product X', 'which SKUs exist for Y', "
            "'variant with size L', 'internal reference of a specific variant'."
        ),
    },

    # ─────────────────────────────────────────
    # VENTES
    # ─────────────────────────────────────────
    "sale.order": {
        "name": "Sales Order / Quotation",
        "description": (
            "Represents a sales order or quotation sent to a customer. "
            "Use for: counting or listing orders, order status (draft/confirmed/done), "
            "revenue per order, orders by customer or date. "
            "Do NOT use when the question targets specific products inside an order."
        ),
    },
    "sale.order.line": {
        "name": "Sales Order Line",
        "description": (
            "Represents a line (product) inside a sales order. "
            "Use ONLY when the question targets specific products, quantities, "
            "or discounts within a sales order. "
            "Do NOT use for counting orders themselves."
        ),
    },

    # ─────────────────────────────────────────
    # ACHATS
    # ─────────────────────────────────────────
    "purchase.order": {
        "name": "Purchase Order",
        "description": (
            "Represents a purchase order sent to a supplier/vendor. "
            "Use for: pending purchases, orders by supplier, total purchased amount, "
            "order status (draft/purchase/done). "
            "Do NOT use when targeting specific items inside the order."
        ),
    },
    "purchase.order.line": {
        "name": "Purchase Order Line",
        "description": (
            "Represents a line (product/article) inside a purchase order. "
            "Use ONLY when the question targets specific items, quantities, "
            "or prices within a purchase order. "
            "Do NOT use for counting or listing purchase orders themselves."
        ),
    },

    # ─────────────────────────────────────────
    # FACTURATION & COMPTABILITÉ
    # ─────────────────────────────────────────
    "account.move": {
        "name": "Invoice / Vendor Bill / Journal Entry",
        "description": (
            "Covers ALL accounting documents: customer invoices, vendor bills, "
            "credit notes (avoirs), and journal entries. "
            "Distinguish type via move_type field internally — always pick this model. "
            "Use for: unpaid invoices, vendor bills this month, credit notes, "
            "journal entries, overdue invoices. "
            "Do NOT use for actual payment transactions."
        ),
    },
    "account.payment": {
        "name": "Payment",
        "description": (
            "Represents an explicit payment transaction (money received or sent). "
            "Use for: payments received from customers, payments sent to suppliers, "
            "bank payments, cash payments. "
            "Do NOT use for invoices or bills — those are account.move."
        ),
    },
    "account.account": {
        "name": "Chart of Accounts",
        "description": (
            "Represents an accounting account in the chart of accounts (plan comptable). "
            "Use for: listing accounts, looking up account codes or labels, "
            "account 401, account structure. "
            "Do NOT use for invoices or payments."
        ),
    },
    "account.journal": {
        "name": "Accounting Journal (configuration)",
        "description": (
            "Represents a journal configuration (bank journal, sales journal, etc.). "
            "Use ONLY when asking about journal setup or configuration. "
            "Do NOT use for journal entries — those are account.move."
        ),
    },
    "account.tax": {
        "name": "Tax",
        "description": (
            "Represents tax rules and rates (VAT, TVA). "
            "Use for: tax rates, VAT configuration, which taxes apply to a product. "
        ),
    },

    # ─────────────────────────────────────────
    # RESSOURCES HUMAINES — EMPLOYÉS
    # ─────────────────────────────────────────
    "hr.employee": {
        "name": "Employee",
        "description": (
            "Represents an employee profile. "
            "Use for: employee list, headcount, employee by department or job position, "
            "employee contact or personal info. "
            "Do NOT use for absences or payslips — those have dedicated models."
        ),
    },
    "hr.department": {
        "name": "Department",
        "description": (
            "Represents an organizational department. "
            "Use for: listing departments, department structure. "
            "For employees in a department, use hr.employee filtered by department."
        ),
    },
    "hr.job": {
        "name": "Job Position",
        "description": (
            "Represents a job position or title configuration. "
            "Use for: listing job positions, available roles. "
            "Do NOT use for employee records."
        ),
    },
    "hr.contract": {
        "name": "Employment Contract",
        "description": (
            "Represents an employment contract with wage and contract dates. "
            "Use for: contractual salary (salaire contractuel), contract start/end dates, "
            "wage per employee. "
            "Do NOT use for computed pay — that is hr.payslip."
        ),
    },

    # ─────────────────────────────────────────
    # CONGÉS
    # ─────────────────────────────────────────
    "hr.leave": {
        "name": "Leave Request / Time Off",
        "description": (
            "Represents a leave or time-off request submitted by an employee. "
            "Use for: who is on leave, pending leave requests, vacation requests, "
            "sick days, leave validation, absences. "
        ),
    },
    "hr.leave.allocation": {
        "name": "Leave Allocation",
        "description": (
            "Represents the number of leave days allocated to an employee. "
            "Use for: leave balance, how many vacation days an employee has, "
            "leave quota, solde de congés. "
            "Do NOT use for actual leave requests — that is hr.leave."
        ),
    },
    "hr.leave.type": {
        "name": "Leave Type",
        "description": (
            "Represents a type/category of leave (annual leave, sick leave, etc.). "
            "Use for: listing leave types, leave type configuration."
        ),
    },

    # ─────────────────────────────────────────
    # PAIE
    # ─────────────────────────────────────────
    "hr.payslip": {
        "name": "Payslip",
        "description": (
            "Represents a computed payslip (fiche de paie / bulletin de salaire). "
            "Use for: payslip for an employee, salary this month, pay computation. "
            "Do NOT use for contractual wage — that is hr.contract."
        ),
    },
    "hr.payslip.run": {
        "name": "Payslip Batch",
        "description": (
            "Represents a batch of payslips processed together (payroll run). "
            "Use for: payslip batch, payroll run for a given month, lot de bulletins."
        ),
    },

    # ─────────────────────────────────────────
    # PROJET & TÂCHES
    # ─────────────────────────────────────────
    "project.project": {
        "name": "Project",
        "description": (
            "Represents a project. "
            "Use for: listing projects, project status, project manager, "
            "number of projects, project deadlines."
        ),
    },
    "project.task": {
        "name": "Task",
        "description": (
            "Represents a task inside a project. "
            "Use for: listing tasks, task status (new/in progress/done), "
            "tasks assigned to a user, overdue tasks, task count per project."
        ),
    },

    # ─────────────────────────────────────────
    # CONTACTS
    # ─────────────────────────────────────────
    "res.partner": {
        "name": "Contact / Customer / Supplier",
        "description": (
            "Represents any external party: customer, supplier, vendor, contact. "
            "Use customer_rank > 0 for customers, supplier_rank > 0 for suppliers. "
            "Use for: customer list, supplier address, contact info, active vendors. "
            "Do NOT use for employees (hr.employee) or system users (res.users)."
        ),
    },
    "res.users": {
        "name": "System User",
        "description": (
            "Represents an internal Odoo system user (login account). "
            "Use for: who can log in, user list, user access rights. "
            "Do NOT use for employees or contacts."
        ),
    },
}
