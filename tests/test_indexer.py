from pathlib import Path

from genai.indexer import format_model_doc, load_model_docs, load_examples

MODELS_YML = """
version: 2
models:
  - name: fct_trips
    description: "Trip fact table at one-row-per-trip grain."
    columns:
      - name: trip_key
        description: "Deterministic surrogate key (primary key)."
      - name: fare_amount
        description: "Metered fare in USD."
  - name: stg_trips
    description: "Cleaned staging view."
    columns:
      - name: trip_key
        description: "Surrogate key."
"""

EXAMPLES_YML = """
examples:
  - question: "Ile było przejazdów?"
    sql: "SELECT COUNT(*) AS trips FROM `taxi-chat-data.marts.fct_trips`"
"""


def test_format_model_doc_prefixes_dataset_and_lists_columns():
    doc = format_model_doc(
        name="fct_trips",
        description="Trip fact table.",
        columns=[{"name": "trip_key", "description": "PK."}],
    )
    assert doc.startswith("Table marts.fct_trips: Trip fact table.")
    assert "- trip_key: PK." in doc


def test_format_model_doc_maps_stg_prefix_to_staging_dataset():
    doc = format_model_doc(name="stg_trips", description="Staging.", columns=[])
    assert doc.startswith("Table staging.stg_trips:")


def test_load_model_docs_reads_yaml_files(tmp_path: Path):
    (tmp_path / "marts").mkdir()
    (tmp_path / "marts" / "_marts__models.yml").write_text(MODELS_YML)
    docs = load_model_docs(tmp_path)
    ids = [d["id"] for d in docs]
    assert ids == ["marts.fct_trips", "staging.stg_trips"]
    assert "fare_amount" in docs[0]["text"]


def test_load_examples_formats_question_sql_pairs(tmp_path: Path):
    path = tmp_path / "examples.yml"
    path.write_text(EXAMPLES_YML)
    examples = load_examples(path)
    assert len(examples) == 1
    assert examples[0]["id"] == "example-1"
    assert examples[0]["text"] == (
        "QUESTION: Ile było przejazdów?\n"
        "SQL: SELECT COUNT(*) AS trips FROM `taxi-chat-data.marts.fct_trips`"
    )
