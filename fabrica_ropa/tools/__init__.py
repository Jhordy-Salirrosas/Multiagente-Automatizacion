"""Herramientas externas usadas por los agentes.

Expone tanto las clases originales como las funciones @tool de LangChain
para integración con agentes LangChain.

Proceso 1: EmailTool, SheetsTool
Proceso 2: PaymentTool, BudgetTool, PurchaseTool, ProductionTool
"""
from tools.email_tool import EmailTool, send_email_notification
from tools.sheets_tool import SheetsTool, save_order_to_db
from tools.payment_tool import PaymentTool, process_payment
from tools.budget_tool import BudgetTool, estimate_budget
from tools.purchase_tool import PurchaseTool, purchase_materials
from tools.production_tool import ProductionTool, notify_production

# Lista de tools LangChain disponibles para bind_tools()
LANGCHAIN_TOOLS = [
    # Proceso 1
    send_email_notification,
    save_order_to_db,
    # Proceso 2
    process_payment,
    estimate_budget,
    purchase_materials,
    notify_production,
]

