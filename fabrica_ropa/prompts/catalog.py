"""
Catálogo de Prompts Versionado — §6 de la plantilla.

Los prompts evolucionan y son artefactos versionables: se tratan como código,
con historial y resultado de evaluación de cada versión.

Uso:
    from prompts.catalog import get_prompt, PROMPT_REGISTRY

    prompt_text = get_prompt("P-validator", version=2)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class PromptVersion:
    """Registro de una versión de un prompt."""
    version: int
    text: str
    description: str
    metric_score: Optional[float] = None   # % de exactitud en golden set
    notes: str = ""


@dataclass
class PromptEntry:
    """Entrada del catálogo: un prompt con todas sus versiones."""
    prompt_id: str
    purpose: str
    versions: list[PromptVersion] = field(default_factory=list)

    @property
    def latest_version(self) -> int:
        return max(v.version for v in self.versions) if self.versions else 0

    def get_version(self, version: Optional[int] = None) -> PromptVersion:
        """Devuelve una versión específica o la más reciente."""
        if version is None:
            version = self.latest_version
        for v in self.versions:
            if v.version == version:
                return v
        raise ValueError(f"Versión {version} no existe para prompt '{self.prompt_id}'")


# =============================================================================
# REGISTRO GLOBAL DE PROMPTS
# =============================================================================

PROMPT_REGISTRY: dict[str, PromptEntry] = {}


def _register(prompt_id: str, purpose: str, versions: list[PromptVersion]) -> None:
    """Registra un prompt en el catálogo global."""
    PROMPT_REGISTRY[prompt_id] = PromptEntry(
        prompt_id=prompt_id,
        purpose=purpose,
        versions=versions,
    )


# ─────────────────────────────────────────────────────────────────────────────
# P-validator: Validación de rubro textil
# ─────────────────────────────────────────────────────────────────────────────
_register("P-validator", "Valida si el pedido es del rubro textil", [
    PromptVersion(
        version=1,
        text=(
            'Eres un agente que decide si un mensaje es sobre ropa. '
            'Responde con JSON: {"is_textile": true/false, "reason": "..."}'
        ),
        description="Versión base, instrucciones mínimas",
        metric_score=0.78,
        notes="Baja precisión en mensajes ambiguos (saludos)",
    ),
    PromptVersion(
        version=2,
        text=(
            'Eres un agente especializado EXCLUSIVAMENTE en validar si un '
            'mensaje de un cliente corresponde al rubro TEXTIL (confección de ropa: '
            'polos, camisas, pantalones, casacas, vestidos, uniformes, faldas, shorts, etc.).\n\n'
            'Tu ÚNICA función es responder con un JSON estricto, sin texto adicional:\n\n'
            '{\n'
            '  "is_textile": true | false,\n'
            '  "reason": "explicación breve en español (máx 1 línea)",\n'
            '  "confidence": 0.0 a 1.0\n'
            '}\n\n'
            'Reglas:\n'
            '- Si el cliente pide prendas de vestir, accesorios textiles, uniformes → is_textile=true\n'
            '- Si pide comida, electrónica, vehículos, muebles → is_textile=false\n'
            '- Si el mensaje es ambiguo (saludo "hola") → is_textile=true con confidence=0.5\n'
            '- NUNCA respondas con texto fuera del JSON. NUNCA uses ```json fences.'
        ),
        description="Añade confidence, reglas explícitas para ambigüedad, formato estricto",
        metric_score=0.93,
        notes="Mejora significativa con el campo confidence y reglas de ambigüedad",
    ),
])

# ─────────────────────────────────────────────────────────────────────────────
# P-collector: Recolección conversacional de datos
# ─────────────────────────────────────────────────────────────────────────────
_register("P-collector", "Recolecta los 8 datos del pedido vía conversación", [
    PromptVersion(
        version=1,
        text=(
            'Eres un agente conversacional que recolecta datos para un pedido textil. '
            'Debes recoger: nombre, email, tipo_prenda, cantidad, talla, color, acabado, fecha_entrega. '
            'Responde con JSON: {"extracted_data": {...}, "reply": "..."}'
        ),
        description="Versión base, instrucciones mínimas",
        metric_score=0.72,
        notes="El LLM a veces inventa datos o no respeta el formato JSON",
    ),
    PromptVersion(
        version=2,
        text=(
            'Eres un agente conversacional especializado en recolectar '
            'datos para un pedido de confección textil. Debes recoger 8 datos:\n\n'
            '1. nombre           (texto)\n'
            '2. email            (texto con @)\n'
            '3. tipo_prenda      (polo, camisa, pantalón, casaca, vestido, uniforme, falda, short)\n'
            '4. cantidad         (entero ≥ 1)\n'
            '5. talla            (XS/S/M/L/XL/XXL o múltiples ej. "25 S y 25 M")\n'
            '6. color            (texto)\n'
            '7. acabado          ("ninguno" | "estampado" | "bordado")\n'
            '8. fecha_entrega    (formato ISO YYYY-MM-DD)\n\n'
            'REGLAS ESTRICTAS:\n'
            '- Responde SIEMPRE con JSON: {"extracted_data": {...}, "reply": "..."}\n'
            '- Solo incluye campos que el cliente mencionó explícitamente\n'
            '- NUNCA inventes datos. NUNCA uses ```json fences.\n\n'
            'Formato exacto:\n'
            '{"extracted_data": {"nombre": "Juan"}, "reply": "Gracias Juan. ¿Tu correo?"}'
        ),
        description="Tipos explícitos, regla anti-alucinación, formato con ejemplo",
        metric_score=0.91,
        notes="Mejora sustancial al listar tipos y agregar regla anti-invención",
    ),
])

# ─────────────────────────────────────────────────────────────────────────────
# P-pricing: Formato de cotización
# ─────────────────────────────────────────────────────────────────────────────
_register("P-pricing", "Genera resumen amable de cotización", [
    PromptVersion(
        version=1,
        text=(
            'Eres un agente de cotización para una fábrica de ropa. '
            'Recibes un JSON con los números YA CALCULADOS y debes generar un resumen '
            'amable y claro en texto plano en español.\n\n'
            'Reglas:\n'
            '- Solo formateas el texto. Los números YA están calculados; NO los cambies.\n'
            '- Incluye: producto, cantidad, precio unitario, subtotal, descuento, total y adelanto.\n'
            '- Termina preguntando: "¿Confirmas para registrar el pedido?"\n'
            '- Devuelve SOLO el texto del resumen, sin JSON ni fences.'
        ),
        description="Versión única, instrucciones claras anti-modificación de números",
        metric_score=0.95,
        notes="Alta precisión porque los números vienen precalculados",
    ),
])

# ─────────────────────────────────────────────────────────────────────────────
# P-notifier: Email de constancia
# ─────────────────────────────────────────────────────────────────────────────
_register("P-notifier", "Genera HTML de constancia de pedido", [
    PromptVersion(
        version=1,
        text=(
            'Eres un agente de notificación. Genera el CUERPO HTML '
            '(sin <html>, <head>, ni <body>; solo el contenido interno) de una '
            'constancia formal de pedido en español, profesional y limpio. Usa <h2>, <p>, '
            '<ul>, <table> según convenga. Devuelve SOLO el HTML, sin fences markdown.'
        ),
        description="Versión única, instrucciones de formato HTML",
        metric_score=0.88,
        notes="Funciona bien pero a veces incluye fences markdown",
    ),
])

# ─────────────────────────────────────────────────────────────────────────────
# P-rag-responder: Respuesta con contexto RAG
# ─────────────────────────────────────────────────────────────────────────────
_register("P-rag-responder", "Genera respuesta basada en contexto recuperado (RAG)", [
    PromptVersion(
        version=1,
        text=(
            'Eres un asistente de ventas de una fábrica de ropa. '
            'Responde la pregunta del cliente usando EXCLUSIVAMENTE la información '
            'del contexto proporcionado.\n\n'
            'REGLAS:\n'
            '- Responde en español, de forma amable y concisa.\n'
            '- Si el contexto no contiene la respuesta, di "No tengo esa información".\n'
            '- NUNCA inventes datos que no estén en el contexto.\n'
            '- Cita los datos relevantes del catálogo.\n\n'
            'CONTEXTO:\n{context}\n\n'
            'PREGUNTA: {question}\n\n'
            'RESPUESTA:'
        ),
        description="Template RAG con anti-alucinación y instrucción de citar contexto",
        metric_score=0.90,
        notes="Buen groundedness; el formato {context}/{question} se reemplaza en runtime",
    ),
])

# ─────────────────────────────────────────────────────────────────────────────
# P-deep-planner: Planificador del Deep Agent
# ─────────────────────────────────────────────────────────────────────────────
_register("P-deep-planner", "Planifica tareas complejas descomponiéndolas en pasos", [
    PromptVersion(
        version=1,
        text=(
            'Eres un agente planificador experto. Tu rol es descomponer tareas complejas '
            'en pasos concretos y asignarlos a sub-agentes especializados.\n\n'
            'Sub-agentes disponibles:\n'
            '- Investigador: busca y sintetiza información del catálogo\n'
            '- Redactor: estructura respuestas formales y documentos\n'
            '- Crítico: evalúa calidad contra criterios de completitud y exactitud\n\n'
            'Responde con JSON:\n'
            '{\n'
            '  "objetivo": "descripción breve",\n'
            '  "pasos": ["paso 1", "paso 2", ...],\n'
            '  "sub_agentes_requeridos": ["Investigador", "Redactor"],\n'
            '  "complejidad_estimada": "baja|media|alta"\n'
            '}\n\n'
            'TAREA: {task}'
        ),
        description="Planificador con catálogo de sub-agentes y formato JSON",
        metric_score=0.85,
        notes="Funciona bien para tareas de 3-5 pasos; sobre-planifica tareas simples",
    ),
])


# =============================================================================
# API PÚBLICA
# =============================================================================

def get_prompt(prompt_id: str, version: Optional[int] = None) -> str:
    """
    Obtiene el texto de un prompt por su ID y versión.

    Args:
        prompt_id: Identificador del prompt (ej. "P-validator").
        version: Versión específica (None = última).

    Returns:
        Texto del prompt.
    """
    if prompt_id not in PROMPT_REGISTRY:
        raise KeyError(f"Prompt '{prompt_id}' no encontrado. "
                       f"Disponibles: {list(PROMPT_REGISTRY.keys())}")
    entry = PROMPT_REGISTRY[prompt_id]
    return entry.get_version(version).text


def list_prompts() -> list[dict]:
    """Lista todos los prompts del catálogo con metadata."""
    result = []
    for pid, entry in PROMPT_REGISTRY.items():
        for v in entry.versions:
            result.append({
                "prompt_id": pid,
                "purpose": entry.purpose,
                "version": v.version,
                "description": v.description,
                "metric_score": v.metric_score,
                "notes": v.notes,
                "latest": v.version == entry.latest_version,
            })
    return result
