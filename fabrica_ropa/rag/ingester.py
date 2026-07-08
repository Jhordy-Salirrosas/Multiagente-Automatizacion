"""
Ingester — Carga, chunking y almacenamiento de documentos en ChromaDB.

Implementa §3.3 de la plantilla usando componentes LangChain:
  - Estrategia de chunking: RecursiveCharacterTextSplitter, 800 tokens (~3200 chars), overlap 120 tokens
  - Modelo de embeddings: HuggingFaceEmbeddings (sentence-transformers, local, gratuito)
  - Vector store: Chroma de LangChain (local, sin servidor externo)
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

# Parámetros de chunking (§3.3)
CHUNK_SIZE_CHARS = 3200       # ~800 tokens (4 chars/token aprox)
CHUNK_OVERLAP_CHARS = 480     # ~120 tokens
COLLECTION_NAME = "fabrica_ropa_docs"

# Directorio de documentos
DOCUMENTS_DIR = Path(__file__).resolve().parent / "documents"

# Directorio de persistencia de ChromaDB
CHROMA_PERSIST_DIR = Path(__file__).resolve().parent / ".chroma_db"

# Cache global de embeddings y vectorstore
_EMBEDDINGS = None
_VECTORSTORE = None


def _get_embeddings():
    """Carga lazy del modelo de embeddings usando LangChain HuggingFaceEmbeddings."""
    global _EMBEDDINGS
    if _EMBEDDINGS is None:
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            # Modelo ligero y multilingüe, buen balance calidad/velocidad
            _EMBEDDINGS = HuggingFaceEmbeddings(
                model_name="all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
            print("[OK] Embeddings LangChain cargados: all-MiniLM-L6-v2")
        except ImportError:
            print("[WARN] langchain-community o sentence-transformers no instalado.")
            _EMBEDDINGS = None
    return _EMBEDDINGS


def _get_vectorstore(embeddings=None):
    """Obtiene o crea el vectorstore Chroma vía LangChain."""
    global _VECTORSTORE
    if _VECTORSTORE is not None:
        return _VECTORSTORE
    if embeddings is None:
        embeddings = _get_embeddings()
    if embeddings is None:
        return None
    try:
        from langchain_community.vectorstores import Chroma
        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _VECTORSTORE = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(CHROMA_PERSIST_DIR),
        )
        print(f"[OK] Chroma LangChain inicializado en {CHROMA_PERSIST_DIR}")
        return _VECTORSTORE
    except ImportError:
        print("[WARN] chromadb o langchain-community no instalado. RAG no disponible.")
        return None


def _get_text_splitter():
    """Crea el splitter LangChain RecursiveCharacterTextSplitter."""
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        return RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE_CHARS,
            chunk_overlap=CHUNK_OVERLAP_CHARS,
            separators=["\n\n\n", "\n\n", "\n", ". ", " "],
            length_function=len,
        )
    except ImportError:
        print("[WARN] langchain-text-splitters no instalado.")
        return None


def load_documents(directory: Optional[Path] = None) -> list[dict]:
    """
    Carga todos los documentos .txt del directorio especificado.

    Retorna una lista de dicts con 'content', 'source' y 'chunks'.
    """
    if directory is None:
        directory = DOCUMENTS_DIR

    splitter = _get_text_splitter()
    documents = []
    for filepath in sorted(directory.glob("*.txt")):
        content = filepath.read_text(encoding="utf-8")
        if splitter:
            chunks = splitter.split_text(content)
        else:
            # Fallback bruto si no hay splitter
            chunks = [content[i:i + CHUNK_SIZE_CHARS]
                      for i in range(0, len(content), CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS)]
        documents.append({
            "source": filepath.name,
            "content": content,
            "chunks": chunks,
        })
        print(f"📄 Cargado: {filepath.name} → {len(chunks)} chunks")

    return documents


def ingest(force: bool = False) -> int:
    """
    Pipeline completo de ingesta con LangChain:
    1. Carga documentos del directorio
    2. Los divide en chunks con RecursiveCharacterTextSplitter
    3. Genera embeddings con HuggingFaceEmbeddings
    4. Los almacena en Chroma vía LangChain

    Args:
        force: Si True, recrea la colección desde cero.

    Returns:
        Número total de chunks ingestados.
    """
    global _VECTORSTORE

    embeddings = _get_embeddings()
    if embeddings is None:
        print("[WARN] Embeddings no disponibles. Saltando ingesta.")
        return 0

    try:
        from langchain_community.vectorstores import Chroma
    except ImportError:
        print("[WARN] Chroma no disponible. Saltando ingesta.")
        return 0

    # Si force, eliminar la colección existente
    if force:
        import shutil
        if CHROMA_PERSIST_DIR.exists():
            shutil.rmtree(CHROMA_PERSIST_DIR, ignore_errors=True)
            print(f"🗑️  Directorio Chroma eliminado (force=True)")
        _VECTORSTORE = None

    # Verificar si ya tiene datos
    vs = _get_vectorstore(embeddings)
    if vs is not None and not force:
        try:
            existing = vs._collection.count()
            if existing > 0:
                print(f"[INFO] Colección ya tiene {existing} documentos. Usa force=True para reingestar.")
                return existing
        except Exception:
            pass

    # Cargar y procesar documentos
    documents = load_documents()
    if not documents:
        print("[WARN] No se encontraron documentos para ingestar.")
        return 0

    total_chunks = 0
    all_texts = []
    all_metadatas = []

    for doc in documents:
        chunks = doc["chunks"]
        if not chunks:
            continue
        for i, chunk in enumerate(chunks):
            all_texts.append(chunk)
            all_metadatas.append({"source": doc["source"], "chunk_index": i})
        total_chunks += len(chunks)
        print(f"  [OK] {doc['source']}: {len(chunks)} chunks preparados")

    if all_texts:
        # Crear vectorstore desde los textos (reemplaza el existente)
        _VECTORSTORE = None  # Resetear cache
        CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _VECTORSTORE = Chroma.from_texts(
            texts=all_texts,
            embedding=embeddings,
            metadatas=all_metadatas,
            collection_name=COLLECTION_NAME,
            persist_directory=str(CHROMA_PERSIST_DIR),
        )

    print(f"\n🎉 Ingesta completa: {total_chunks} chunks en colección '{COLLECTION_NAME}'")
    return total_chunks


# =============================================================================
# CLI de ingesta
# =============================================================================
if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    ingest(force=force)
