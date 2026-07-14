import os
from pathlib import Path
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from core.mcp_messages import OrderData

class PDFTool:
    """Herramienta para generar documentos PDF determinísticamente."""

    def __init__(self, output_dir: str = "data/comprobantes"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_quote_pdf(self, order: OrderData, quote_data: dict) -> str:
        """Genera un PDF con la cotización del pedido."""
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)

        # Header
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(200, 10, text="Fábrica de Ropa - Cotización Oficial", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(10)

        # Body
        pdf.set_font("Helvetica", size=12)
        cliente = order.nombre if order.nombre else "Cliente no registrado"
        
        pdf.cell(200, 10, text=f"Cliente: {cliente}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"Producto: {quote_data.get('producto', '')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"Cantidad: {quote_data.get('cantidad', 0)} unidades", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.ln(5)
        pdf.cell(200, 10, text="Desglose de costos:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"- Precio Unitario Base: S/ {quote_data.get('precio_unitario', 0):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"- Costo Acabado Unitario: S/ {quote_data.get('costo_acabado_unitario', 0):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"- Subtotal: S/ {quote_data.get('subtotal', 0):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"- Descuento ({quote_data.get('descuento_label', '')}): -S/ {quote_data.get('descuento_monto', 0):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.ln(5)
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(200, 10, text=f"TOTAL A PAGAR: S/ {quote_data.get('total', 0):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"Adelanto Requerido (50%): S/ {quote_data.get('adelanto', 0):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.ln(15)
        pdf.set_font("Helvetica", 'I', 10)
        pdf.cell(200, 10, text="Este documento es generado automaticamente y es valido por 15 dias.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        filename = f"cotizacion_{order.tipo_prenda}_{quote_data.get('total', 0)}.pdf"
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
        filepath = self.output_dir / filename
        
        # Guardar (fpdf soporta utf-8 configurando fuentes, pero con Arial estándar mejor quitar acentos o dejar que fpdf2 lo maneje si no falla)
        try:
            pdf.output(str(filepath))
        except Exception as e:
            # fpdf2 soporta utf-8 by default in text
            pdf.output(str(filepath))

        return str(filepath.absolute())

    def generate_receipt_pdf(self, pedido_id: str, quote_result, cliente_nombre: str) -> str:
        """Genera un PDF con la boleta electrónica."""
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)

        # Header
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(200, 10, text="Fábrica de Ropa - Boleta Electrónica", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(10)

        # Body
        pdf.set_font("Helvetica", size=12)
        pdf.cell(200, 10, text=f"Pedido ID: {pedido_id}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(200, 10, text=f"Cliente: {cliente_nombre}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        if quote_result:
            pdf.cell(200, 10, text=f"Monto Total: S/ {quote_result.total:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(200, 10, text=f"Adelanto Pagado: S/ {quote_result.adelanto:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(200, 10, text=f"Saldo Pendiente: S/ {quote_result.total - quote_result.adelanto:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.ln(15)
        pdf.set_font("Helvetica", 'I', 10)
        pdf.cell(200, 10, text="Gracias por su compra.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        filepath = self.output_dir / f"boleta_{pedido_id}.pdf"
        pdf.output(str(filepath))

        return str(filepath.absolute())
