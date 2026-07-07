"""
conftest.py — Configuración común de tests.

Fuerza el modo mock para que los tests corran sin necesidad de API key.
"""
import os
import sys
from pathlib import Path

# Forzar mock ANTES de cualquier import del proyecto
os.environ["EXECUTION_MODE"] = "mock"
os.environ.setdefault("LLM_API_KEY", "mock-key")

# Asegurar que el paquete sea importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
