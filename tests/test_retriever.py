from pathlib import Path

import chromadb

from genai.indexer import EXAMPLES_COLLECTION, SCHEMA_COLLECTION
from genai.retriever import Retriever
from genai.types import SchemaContext


class FakeEmbedder:
    """Deterministic 2-d embeddings: 'trips'-themed texts → x-axis, others → y."""

    def embed(self, texts):
        return [[1.0, 0.0] if "trip" in t.lower() else [0.0, 1.0] for t in texts]


def _seed_chroma(chroma_dir: Path, embedder: FakeEmbedder):
    client = chromadb.PersistentClient(path=str(chroma_dir))
    schema_texts = ["Table marts.fct_trips: trips fact", "Table marts.dim_payment: payments"]
    client.create_collection(SCHEMA_COLLECTION).add(
        ids=["marts.fct_trips", "marts.dim_payment"],
        documents=schema_texts,
        embeddings=embedder.embed(schema_texts),
    )
    example_texts = [
        "QUESTION: Ile było trip?\nSQL: SELECT 1",
        "QUESTION: platnosci?\nSQL: SELECT 2",
    ]
    client.create_collection(EXAMPLES_COLLECTION).add(
        ids=["example-1", "example-2"],
        documents=example_texts,
        embeddings=embedder.embed(example_texts),
    )


def test_retrieve_returns_most_similar_docs_first(tmp_path: Path):
    embedder = FakeEmbedder()
    _seed_chroma(tmp_path, embedder)
    retriever = Retriever(chroma_dir=tmp_path, embedder=embedder)
    ctx = retriever.retrieve("ile bylo trip?", k_schema=1, k_examples=1)
    assert isinstance(ctx, SchemaContext)
    assert ctx.tables == ["Table marts.fct_trips: trips fact"]
    assert ctx.examples == ["QUESTION: Ile było trip?\nSQL: SELECT 1"]


def test_retrieve_caps_k_at_collection_size(tmp_path: Path):
    embedder = FakeEmbedder()
    _seed_chroma(tmp_path, embedder)
    retriever = Retriever(chroma_dir=tmp_path, embedder=embedder)
    ctx = retriever.retrieve("cokolwiek", k_schema=10, k_examples=10)
    assert len(ctx.tables) == 2
    assert len(ctx.examples) == 2
