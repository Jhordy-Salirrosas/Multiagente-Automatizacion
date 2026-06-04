"""
Ingester — Carga, chunking y almacenamiento de documentos en ChromaDB.

Implementa §3.3 de la plantilla:
  - Estrategia de chunking: Recursive, 800 tokens (~3200 chars), overlap 120 tokens
  - Modelo de embeddings: sentence-transformers (local, gratuito)
  - Vector store: ChromaDB (local, sin servidor externo)
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Optional

# Lazy imports para que el módulo sea importable sin las dependencias pesadas
_CHROMA_CLIENT = None
_EMBED_MODEL = None

# Parámetros de chunking (§3.3)
CHUNK_SIZE_CHARS = 3200       # ~800 tokens (4 chars/token aprox)
CHUNK_OVERLAP_CHARS = 480     # ~120 tokens
COLLECTION_NAME = "fabrica_ropa_docs"

# Directorio de documentos
DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"

# Directorio de persistencia de ChromaDB
CHROMA_PERSIST_DIR = Path(__file__).resolve().parent / ".chroma_db"


def _get_embed_model():
    """Carga lazy del modelo de embeddings (sentence-transformers)."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Modelo ligero y multilingüe, buen balance calidad/velocidad
            _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            print("✅ Modelo de embeddings cargado: all-MiniLM-L6-v2")
        except ImportError:
            print("⚠️  sentence-transformers no instalado. Usando embeddings mock.")
            _EMBED_MODEL = None
    return _EMBED_MODEL


def _get_chroma_client():
    """Obtiene o crea el cliente ChromaDB persistente."""
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        try:
            import chromadb
            CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
            _CHROMA_CLIENT = chromadb.PersistentClient(
                path=str(CHROMA_PERSIST_DIR)
            )
            print(f"✅ ChromaDB inicializado en {CHROMA_PERSIST_DIR}")
        except ImportError:
            print("⚠️  chromadb no instalado. RAG no disponible.")
            _CHROMA_CLIENT = None
    return _CHROMA_CLIENT


class EmbeddingFunction:
    """Wrapper de sentence-transformers para ChromaDB."""

    def __init__(self):
        self.model = _get_embed_model()

    def __call__(self, input: list[str]) -> list[list[float]]:
        if self.model is None:
            # Embeddings mock: vectores aleatorios de 384 dimensiones
            import random
            return [[random.uniform(-1, 1) for _ in range(384)] for _ in input]
        embeddings = self.model.encode(input, show_progress_bar=False)
        return embeddings.tolist()


def recursive_chunk(text: str, chunk_size: int = CHUNK_SIZE_CHARS,
                    overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """
    Divide texto en chunks con estrategia recursiva.

    Intenta dividir por los separadores más grandes primero (secciones),
    y baja a párrafos y líneas solo si es necesario.
    """
    separators = [
        "\n\n\n",     # Secciones mayores
        "\n\n",       # Párrafos
        "\n",         # Líneas
        ". ",         # Oraciones
        " ",          # Palabras
    ]

    chunks: list[str] = []

    def _split_recursive(text: str, sep_idx: int = 0) -> list[str]:
        """Divide recursivamente usando separadores de mayor a menor."""
        if len(text) <= chunk_size:
            return [text.strip()] if text.strip() else []

        if sep_idx >= len(separators):
            # Sin más separadores: cortar bruto
            result = []
            for i in range(0, len(text), chunk_size - overlap):
                piece = text[i:i + chunk_size].strip()
                if piece:
                    result.append(piece)
            return result

        sep = separators[sep_idx]
        parts = text.split(sep)

        result = []
        current = ""
        for part in parts:
            candidate = (current + sep + part).strip() if current else part.strip()
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current.strip():
                    result.append(current.strip())
                if len(part) > chunk_size:
                    # Recursión con separador más fino
                    result.extend(_split_recursive(part.strip(), sep_idx + 1))
                    current = ""
                else:
                    current = part.strip()

        if current.strip():
            result.append(current.strip())
        return result

    raw_chunks = _split_recursive(text)

    # Aplicar overlap: cada chunk incluye el final del anterior
    final_chunks = []
    for i, chunk in enumerate(raw_chunks):
        if i > 0 and overlap > 0:
            prev_tail = raw_chunks[i - 1][-overlap:]
            chunk = prev_tail + " " + chunk
        final_chunks.append(chunk.strip())

    return final_chunks


def load_documents(directory: Optional[Path] = None) -> list[dict]:
    """
    Carga todos los documentos .txt del directorio especificado.

    Retorna una lista de dicts con 'content', 'source' y 'chunks'.
    """
    if directory is None:
        directory = DOCUMENTS_DIR

    documents = []
    for filepath in sorted(directory.glob("*.txt")):
        content = filepath.read_text(encoding="utf-8")
        chunks = recursive_chunk(content)
        documents.append({
            "source": filepath.name,
            "content": content,
            "chunks": chunks,
        })
        print(f"📄 Cargado: {filepath.name} → {len(chunks)} chunks")

    return documents


def ingest(force: bool = False) -> int:
    """
    Pipeline completo de ingesta:
    1. Carga documentos del directorio
    2. Los divide en chunks
    3. Genera embeddings
    4. Los almacena en ChromaDB

    Args:
        force: Si True, recrea la colección desde cero.

    Returns:
        Número total de chunks ingestados.
    """
    client = _get_chroma_client()
    if client is None:
        print("⚠️  ChromaDB no disponible. Saltando ingesta.")
        return 0

    embed_fn = EmbeddingFunction()

    # Crear o obtener la colección
    if force:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"🗑️  Colección '{COLLECTION_NAME}' eliminada (force=True)")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Documentos de la Fábrica de Ropa para RAG"},
    )

    # Verificar si ya tiene datos
    if collection.count() > 0 and not force:
        print(f"ℹ️  Colección ya tiene {collection.count()} documentos. Usa force=True para reingestar.")
        return collection.count()

    # Cargar y procesar documentos
    documents = load_documents()
    if not documents:
        print("⚠️  No se encontraron documentos para ingestar.")
        return 0

    total_chunks = 0
    for doc in documents:
        chunks = doc["chunks"]
        if not chunks:
            continue

        ids = [f"{doc['source']}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": doc["source"], "chunk_index": i} for i in range(len(chunks))]
        embeddings = embed_fn(chunks)

        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        total_chunks += len(chunks)
        print(f"  ✅ {doc['source']}: {len(chunks)} chunks ingestados")

    print(f"\n🎉 Ingesta completa: {total_chunks} chunks en colección '{COLLECTION_NAME}'")
    return total_chunks


# =============================================================================
# CLI de ingesta
# =============================================================================
if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    ingest(force=force)
