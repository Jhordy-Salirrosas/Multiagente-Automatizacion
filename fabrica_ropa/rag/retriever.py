"""
Retriever — Recuperación híbrida (densa + léxica) sobre ChromaDB.

Implementa §3.3 de la plantilla:
  - Método de recuperación: Híbrido denso + léxico (BM25)
  - k (fragmentos): 4
  - Combina scores de similitud semántica (embeddings) y BM25 (TF-IDF)
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from rag.ingester import (
    _get_chroma_client, _get_embed_model,
    COLLECTION_NAME, EmbeddingFunction, ingest,
)


class HybridRetriever:
    """
    Retriever híbrido que combina búsqueda semántica (dense) con BM25 (léxica).

    La búsqueda densa captura similitud de significado, mientras que BM25
    captura coincidencias exactas de palabras clave. La combinación da
    mejor recall que cualquiera de las dos por separado.
    """

    def __init__(self, k: int = 4, dense_weight: float = 0.6):
        """
        Args:
            k: Número de fragmentos a recuperar.
            dense_weight: Peso de la búsqueda densa vs BM25 (0.0 a 1.0).
        """
        self.k = k
        self.dense_weight = dense_weight
        self.bm25_weight = 1.0 - dense_weight
        self._collection = None
        self._bm25 = None
        self._corpus: list[str] = []
        self._corpus_ids: list[str] = []
        self._embed_fn = EmbeddingFunction()
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Inicializa la colección y BM25 de forma lazy."""
        if self._initialized:
            return self._collection is not None

        self._initialized = True
        client = _get_chroma_client()
        if client is None:
            print("⚠️  ChromaDB no disponible. Retriever en modo degradado.")
            return False

        try:
            self._collection = client.get_collection(COLLECTION_NAME)
        except Exception:
            # Colección no existe, intentar ingestar
            print("ℹ️  Colección no encontrada. Ejecutando ingesta automática...")
            count = ingest()
            if count == 0:
                return False
            self._collection = client.get_collection(COLLECTION_NAME)

        # Construir índice BM25 sobre el corpus
        self._build_bm25_index()
        return True

    def _build_bm25_index(self) -> None:
        """Construye el índice BM25 a partir de los documentos en ChromaDB."""
        if self._collection is None:
            return

        # Obtener todos los documentos
        result = self._collection.get(include=["documents"])
        self._corpus = result["documents"] or []
        self._corpus_ids = result["ids"] or []

        if not self._corpus:
            return

        try:
            from rank_bm25 import BM25Okapi
            # Tokenizar por palabras para BM25
            tokenized = [doc.lower().split() for doc in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
            print(f"✅ Índice BM25 construido: {len(self._corpus)} documentos")
        except ImportError:
            print("⚠️  rank-bm25 no instalado. Solo búsqueda densa disponible.")
            self._bm25 = None

    def query(self, question: str, k: Optional[int] = None) -> list[str]:
        """
        Busca los fragmentos más relevantes para una pregunta.

        Combina resultados de búsqueda densa (ChromaDB embeddings) y
        léxica (BM25) para obtener mejor recall.

        Args:
            question: Pregunta del usuario.
            k: Número de resultados (default: self.k).

        Returns:
            Lista de fragmentos de texto relevantes.
        """
        if not self._ensure_initialized():
            return self._fallback_search(question)

        k = k or self.k
        results: dict[str, float] = {}  # doc_text -> combined_score

        # 1) Búsqueda densa (embeddings)
        try:
            dense_results = self._collection.query(
                query_embeddings=self._embed_fn([question]),
                n_results=min(k * 2, len(self._corpus)),
                include=["documents", "distances"],
            )
            if dense_results["documents"]:
                for doc, dist in zip(
                    dense_results["documents"][0],
                    dense_results["distances"][0],
                ):
                    # ChromaDB devuelve distancia L2; convertir a score de similitud
                    score = 1.0 / (1.0 + dist)
                    results[doc] = results.get(doc, 0) + score * self.dense_weight
        except Exception as e:
            print(f"⚠️  Error en búsqueda densa: {e}")

        # 2) Búsqueda léxica (BM25)
        if self._bm25 is not None and self._corpus:
            try:
                tokenized_query = question.lower().split()
                bm25_scores = self._bm25.get_scores(tokenized_query)
                # Normalizar scores BM25
                max_score = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
                for i, score in enumerate(bm25_scores):
                    doc = self._corpus[i]
                    normalized = score / max_score
                    results[doc] = results.get(doc, 0) + normalized * self.bm25_weight
            except Exception as e:
                print(f"⚠️  Error en búsqueda BM25: {e}")

        # 3) Ordenar por score combinado y tomar top-k
        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in sorted_results[:k]]

    def query_with_scores(self, question: str, k: Optional[int] = None
                          ) -> list[tuple[str, float]]:
        """Como query() pero devuelve también los scores."""
        if not self._ensure_initialized():
            fallback = self._fallback_search(question)
            return [(doc, 0.5) for doc in fallback]

        k = k or self.k
        results: dict[str, float] = {}

        # Dense
        try:
            dense_results = self._collection.query(
                query_embeddings=self._embed_fn([question]),
                n_results=min(k * 2, len(self._corpus)),
                include=["documents", "distances"],
            )
            if dense_results["documents"]:
                for doc, dist in zip(
                    dense_results["documents"][0],
                    dense_results["distances"][0],
                ):
                    score = 1.0 / (1.0 + dist)
                    results[doc] = results.get(doc, 0) + score * self.dense_weight
        except Exception:
            pass

        # BM25
        if self._bm25 is not None and self._corpus:
            try:
                tokenized_query = question.lower().split()
                bm25_scores = self._bm25.get_scores(tokenized_query)
                max_score = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
                for i, score in enumerate(bm25_scores):
                    doc = self._corpus[i]
                    normalized = score / max_score
                    results[doc] = results.get(doc, 0) + normalized * self.bm25_weight
            except Exception:
                pass

        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:k]

    def _fallback_search(self, question: str) -> list[str]:
        """
        Búsqueda de último recurso sin ChromaDB/embeddings: keyword matching
        sobre archivos de texto plano.
        """
        docs_dir = Path(__file__).resolve().parent / "documents"
        if not docs_dir.exists():
            return ["No se encontraron documentos para buscar."]

        all_text = ""
        for f in docs_dir.glob("*.txt"):
            all_text += f.read_text(encoding="utf-8") + "\n\n"

        if not all_text:
            return ["No hay contenido disponible."]

        # Dividir en párrafos y buscar los que más keywords comparten
        paragraphs = [p.strip() for p in all_text.split("\n\n") if len(p.strip()) > 50]
        question_words = set(question.lower().split())

        scored = []
        for para in paragraphs:
            para_words = set(para.lower().split())
            overlap = len(question_words & para_words)
            if overlap > 0:
                scored.append((para, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored[:self.k]] or [paragraphs[0]] if paragraphs else []


# Instancia global reutilizable
retriever = HybridRetriever(k=4, dense_weight=0.6)
