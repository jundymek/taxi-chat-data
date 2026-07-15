"""Builds the Chroma index from dbt model descriptions and curated few-shots.

Run manually after schema changes: python -m genai.indexer
dbt YAML files are the single source of truth about the schema — nothing is
duplicated by hand. The raw dataset is deliberately NOT indexed (guardrails
block it anyway).
"""
from pathlib import Path

import chromadb
import yaml

from genai import config

SCHEMA_COLLECTION = "schema_docs"
EXAMPLES_COLLECTION = "few_shot_examples"


def format_model_doc(name: str, description: str, columns: list[dict]) -> str:
    dataset = "staging" if name.startswith("stg_") else "marts"
    lines = [f"Table {dataset}.{name}: {description}", "Columns:"]
    for col in columns:
        lines.append(f"- {col['name']}: {col.get('description', '')}")
    return "\n".join(lines)


def load_model_docs(models_dir: Path = config.DBT_MODELS_DIR) -> list[dict]:
    docs = []
    for yml in sorted(models_dir.rglob("*__models.yml")):
        data = yaml.safe_load(yml.read_text())
        for model in data.get("models", []):
            doc_id = (
                f"staging.{model['name']}" if model["name"].startswith("stg_")
                else f"marts.{model['name']}"
            )
            docs.append({
                "id": doc_id,
                "text": format_model_doc(
                    model["name"], model.get("description", ""), model.get("columns", [])
                ),
            })
    return docs


def load_examples(path: Path = config.EXAMPLES_PATH) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    return [
        {"id": f"example-{i}", "text": f"QUESTION: {ex['question']}\nSQL: {ex['sql']}"}
        for i, ex in enumerate(data["examples"], start=1)
    ]


def build_index(chroma_dir: Path = config.CHROMA_DIR, embedder=None) -> dict:
    if embedder is None:
        from genai.llm_client import LLMClient
        embedder = LLMClient()
    client = chromadb.PersistentClient(path=str(chroma_dir))
    counts = {}
    for collection_name, items in (
        (SCHEMA_COLLECTION, load_model_docs()),
        (EXAMPLES_COLLECTION, load_examples()),
    ):
        # Rebuild from scratch so deleted models/examples disappear.
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        collection = client.create_collection(collection_name)
        texts = [item["text"] for item in items]
        collection.add(
            ids=[item["id"] for item in items],
            documents=texts,
            embeddings=embedder.embed(texts),
        )
        counts[collection_name] = len(items)
    return counts


if __name__ == "__main__":
    for name, count in build_index().items():
        print(f"{name}: {count} documents indexed")
