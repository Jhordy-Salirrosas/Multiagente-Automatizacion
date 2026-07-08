"""
Configuración centralizada del sistema multiagente.

Soporta múltiples proveedores LLM vía litellm:
  - GitHub Models (recomendado, free tier generoso)
  - OpenAI
  - Gemini
  - Anthropic Claude

La selección del proveedor se controla por el .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv  # type: ignore

# Cargar .env si existe
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# =============================================================================
# LLM
# =============================================================================
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "github").lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://models.github.ai/inference")

# Modo de ejecución: "real" | "mock"
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "real").lower()

# =============================================================================
# LangSmith — Tracing y evaluación (§5.3)
# =============================================================================
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "fabrica-ropa-dev")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

# =============================================================================
# Compatibilidad de variables — litellm lee env vars según el prefijo del modelo
# =============================================================================
# Cuando el modelo es "openai/...", litellm lee OPENAI_API_KEY y OPENAI_API_BASE
# Cuando el modelo es "github/...", litellm lee GITHUB_API_KEY
# Cuando el modelo es "gemini/...", litellm lee GEMINI_API_KEY
# Para máxima compatibilidad, exportamos la key bajo TODOS los nombres,
# y el api_base bajo OPENAI_API_BASE (la convención cuando se usa endpoint
# OpenAI-compatible custom como GitHub Models o cualquier otro proxy).
if LLM_API_KEY:
    os.environ["OPENAI_API_KEY"] = LLM_API_KEY
    os.environ["GITHUB_API_KEY"] = LLM_API_KEY
    os.environ["GITHUB_TOKEN"] = LLM_API_KEY
    os.environ["GEMINI_API_KEY"] = LLM_API_KEY
    os.environ["ANTHROPIC_API_KEY"] = LLM_API_KEY

if LLM_API_BASE:
    # litellm respeta OPENAI_API_BASE cuando el modelo lleva prefijo openai/
    os.environ["OPENAI_API_BASE"] = LLM_API_BASE
    os.environ["OPENAI_BASE_URL"] = LLM_API_BASE

# Aliases hacia atrás (algunos módulos del proyecto importan estos nombres)
GEMINI_API_KEY = LLM_API_KEY
GEMINI_MODEL = LLM_MODEL

# =============================================================================
# Persistencia
# =============================================================================
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "pedidos.db"))
EMAILS_OUTPUT_DIR = os.getenv("EMAILS_OUTPUT_DIR", str(BASE_DIR / "data" / "emails_generados"))

# =============================================================================
# Datos del negocio
# =============================================================================
PRICE_TABLE_PATH = BASE_DIR / "data" / "price_table.json"
VALID_GARMENTS_PATH = BASE_DIR / "data" / "valid_garments.json"

# =============================================================================
# Empresa
# =============================================================================
EMPRESA_NOMBRE = "Fábrica de Ropa - Grupo 01"
EMPRESA_EMAIL = "ventas@fabricaropa.com"
EMPRESA_TELEFONO = "+51 999 888 777"
EMPRESA_DIRECCION = "Av. España 1234, Trujillo - Perú"

# =============================================================================
# Métricas
# =============================================================================
METRICS_LOG_PATH = BASE_DIR / "data" / "metrics.jsonl"

# =============================================================================
# RAG — Subsistema de recuperación (§3.3)
# =============================================================================
RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "3200"))     # ~800 tokens
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "480"))  # ~120 tokens
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "4"))
RAG_DENSE_WEIGHT = float(os.getenv("RAG_DENSE_WEIGHT", "0.6"))


def get_langchain_model_name() -> str:
    """
    Devuelve el nombre del modelo para LangChain ChatOpenAI.

    litellm usa prefijos como 'openai/gpt-4o-mini', pero LangChain
    ChatOpenAI espera solo 'gpt-4o-mini'. Aquí lo limpiamos.
    """
    model = LLM_MODEL
    # Remover prefijos de proveedor que litellm usa
    for prefix in ("openai/", "github/", "azure/"):
        if model.startswith(prefix):
            model = model[len(prefix):]
            break
    return model


def get_langchain_llm(temperature: float = 0.3, max_tokens: int = 1024):
    """
    Crea una instancia de ChatOpenAI configurada para el proveedor actual.

    Compatible con GitHub Models, OpenAI directo, y cualquier endpoint
    OpenAI-compatible. Retorna None si no hay API key (modo mock).
    """
    if EXECUTION_MODE != "real" or not LLM_API_KEY:
        return None
    try:
        from langchain_openai import ChatOpenAI  # type: ignore
        return ChatOpenAI(
            model=get_langchain_model_name(),
            api_key=LLM_API_KEY,
            base_url=LLM_API_BASE or None,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except ImportError:
        print("[WARN] langchain-openai no instalado. pip install langchain-openai")
        return None
    except Exception as e:
        print(f"[WARN] Error creando LLM LangChain: {e}")
        return None


def validate_config() -> tuple[bool, str]:
    """Valida que la configuración esté completa para modo real."""
    if EXECUTION_MODE == "real" and not LLM_API_KEY:
        return False, (
            f"❌ LLM_API_KEY no configurado (proveedor: {LLM_PROVIDER}). "
            "Configura tu .env con la API key, o usa EXECUTION_MODE=mock."
        )
    return True, (
        f"✅ Configuración válida · provider={LLM_PROVIDER} · "
        f"model={LLM_MODEL} · base={LLM_API_BASE}"
    )
