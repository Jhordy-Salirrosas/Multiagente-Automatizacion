"""
Email Tool — Simula el envío de correos (Gmail) generando archivos HTML
en disco. El archivo generado puede abrirse en el navegador para visualizar
la "constancia formal" que recibiría el cliente.
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

from config import EMAILS_OUTPUT_DIR, EMPRESA_NOMBRE, EMPRESA_EMAIL, EMPRESA_TELEFONO


class EmailTool:
    """Tool de notificación. Persiste el correo como HTML."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or EMAILS_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "_", text)[:40]

    def send(self, destinatario: str, asunto: str, cuerpo_html: str) -> str:
        """
        Guarda el email en disco simulando el envío.
        Devuelve la ruta del archivo HTML generado.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{self._slugify(destinatario)}.html"
        path = self.output_dir / filename
        full_html = self._wrap_template(destinatario, asunto, cuerpo_html)
        path.write_text(full_html, encoding="utf-8")
        return str(path)

    @staticmethod
    def _wrap_template(destinatario: str, asunto: str, cuerpo: str) -> str:
        """Envuelve el cuerpo en un template HTML completo con headers."""
        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>{asunto}</title>
</head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 20px auto; padding: 0;">
  <div style="background:#f4f4f4;padding:12px 16px;border:1px solid #ddd;font-size:13px;">
    <strong>De:</strong> {EMPRESA_NOMBRE} &lt;{EMPRESA_EMAIL}&gt;<br>
    <strong>Para:</strong> {destinatario}<br>
    <strong>Asunto:</strong> {asunto}<br>
    <strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}
  </div>
  <div style="padding:24px;border:1px solid #ddd;border-top:none;">
    {cuerpo}
    <hr style="margin-top:32px;border:none;border-top:1px solid #eee;">
    <p style="color:#666;font-size:12px;">
      {EMPRESA_NOMBRE}<br>
      📧 {EMPRESA_EMAIL} · 📞 {EMPRESA_TELEFONO}
    </p>
  </div>
</body>
</html>"""
