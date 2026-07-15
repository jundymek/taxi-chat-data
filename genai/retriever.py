"""Retrieves prompt-ready schema context and few-shots from the Chroma index."""
from pathlib import Path

import chromadb

from genai import config
from genai.indexer import EXAMPLES_COLLECTION, SCHEMA_COLLECTION
from genai.types import SchemaContext


class Retriever:
    def __init__(self, chroma_dir: Path = config.CHROMA_DIR, embedder=None):
        if embedder is None:
            from genai.llm_client import LLMClient
            embedder = LLMClient()
        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=str(chroma_dir))

    def retrieve(self, question: str, k_schema: int = 4, k_examples: int = 3) -> SchemaContext:
        query_embedding = self._embedder.embed([question])[0]
        return SchemaContext(
            tables=self._query(SCHEMA_COLLECTION, query_embedding, k_schema),
            examples=self._query(EXAMPLES_COLLECTION, query_embedding, k_examples),
        )

    def _query(self, collection_name: str, embedding: list[float], k: int) -> list[str]:
        collection = self._client.get_collection(collection_name)
        k = min(k, collection.count())
        result = collection.query(query_embeddings=[embedding], n_results=k)
        return result["documents"][0]
