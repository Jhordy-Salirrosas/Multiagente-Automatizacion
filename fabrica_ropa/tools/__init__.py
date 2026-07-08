"""Herramientas externas usadas por los agentes.

Expone tanto las clases originales (EmailTool, SheetsTool) como las
funciones @tool de LangChain para integración con agentes LangChain.
"""
from tools.email_tool import EmailTool, send_email_notification
from tools.sheets_tool import SheetsTool, save_order_to_db

# Lista de tools LangChain disponibles para bind_tools()
LANGCHAIN_TOOLS = [send_email_notification, save_order_to_db]
