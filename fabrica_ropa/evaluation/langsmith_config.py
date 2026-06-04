"""
Configuración de LangSmith — §5.3 de la plantilla.

Configura:
  - Variables de entorno para LangSmith (tracing, API key, proyecto)
  - Convención de nombres: fabrica-ropa-dev, fabrica-ropa-stg, fabrica-ropa-prod
  - Tags y metadata por traza (versión de prompt, modelo, sesión)
  - Política de retención y de PII
"""
from __future__ import annotations
import os
from typing import Optional


# =============================================================================
# Variables de LangSmith
# =============================================================================

LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "fabrica-ropa-dev")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_ENDPOINT = os.getenv(
    "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
)


def setup_langsmith(
    project_name: Optional[str] = None,
    enable_tracing: bool = True,
) -> bool:
    """
    Configura las variables de entorno para LangSmith.

    Args:
        project_name: Nombre del proyecto (ej. "fabrica-ropa-dev").
        enable_tracing: Si True, habilita el tracing.

    Returns:
        True si la configuración fue exitosa.
    """
    api_key = LANGSMITH_API_KEY
    if not api_key:
        print("⚠️  LANGSMITH_API_KEY no configurada. Tracing deshabilitado.")
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return False

    # Configurar variables de entorno (§5.3.1)
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if enable_tracing else "false"
    os.environ["LANGCHAIN_API_KEY"] = api_key
    os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT
    os.environ["LANGCHAIN_PROJECT"] = project_name or LANGSMITH_PROJECT

    print(f"✅ LangSmith configurado: proyecto={os.environ['LANGCHAIN_PROJECT']}, "
          f"tracing={'ON' if enable_tracing else 'OFF'}")
    return True


def get_trace_metadata(
    prompt_version: str = "v2",
    session_id: Optional[str] = None,
) -> dict:
    """
    Genera metadata estándar para cada traza (§5.3.1).

    Tags por traza: versión de prompt, modelo, usuario, sesión.
    """
    from config import LLM_MODEL, LLM_PROVIDER

    metadata = {
        "prompt_version": prompt_version,
        "model": LLM_MODEL,
        "provider": LLM_PROVIDER,
    }
    if session_id:
        metadata["session_id"] = session_id

    return metadata


def get_trace_tags(prompt_id: str = "", environment: str = "dev") -> list[str]:
    """Genera tags estándar para una traza."""
    from config import LLM_MODEL
    tags = [f"env:{environment}", f"model:{LLM_MODEL}"]
    if prompt_id:
        tags.append(f"prompt:{prompt_id}")
    return tags


# =============================================================================
# Verificación de conectividad
# =============================================================================

def check_langsmith_connection() -> tuple[bool, str]:
    """
    Verifica la conexión con LangSmith.

    Returns:
        (success, message)
    """
    if not LANGSMITH_API_KEY:
        return False, "LANGSMITH_API_KEY no configurada"

    try:
        from langsmith import Client
        client = Client(
            api_key=LANGSMITH_API_KEY,
            api_url=LANGSMITH_ENDPOINT,
        )
        # Intentar listar proyectos
        projects = list(client.list_projects(limit=1))
        return True, f"Conectado a LangSmith ({len(projects)} proyecto(s) encontrado(s))"
    except ImportError:
        return False, "langsmith no instalado"
    except Exception as e:
        return False, f"Error de conexión: {e}"
