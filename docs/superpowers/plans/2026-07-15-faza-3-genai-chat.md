# Faza 3: GenAI "chat with data" (RAG + NL2SQL + guardrails) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Harness note:** Tasks 1–3 are designed for PARALLEL execution by independent
> agents (wave 1); Task 4 runs after 1–3 are merged (wave 2); Tasks 0 and 5 run
> in the operator session. Each agent sees only its own task file — the
> **Interfaces** blocks are the contract between tasks.

**Goal:** `python -m genai.ask "pytanie po polsku"` answers questions about the
Faza 2 warehouse: RAG context from Chroma → gemma4 generates SQL → guardrails
validate before execution → BigQuery runs it → gemma4 answers in Polish.

**Architecture:** Hand-rolled thin modules (`llm_client` → Ollama HTTP,
`retriever` → embedded Chroma, `guardrails` → sqlglot + allowlist + BQ dry-run)
orchestrated by a small LangGraph state graph with a validate→regenerate retry
cycle. Design/spec: `docs/superpowers/specs/2026-07-15-faza-3-genai-rag-nl2sql-design.md`.

**Tech Stack:** Python 3 in the existing `.venv`, requests, chromadb (embedded,
`data/chroma/`), sqlglot, langgraph, pyyaml, google-cloud-bigquery (already
installed), Ollama on the host (`gemma4:latest`, `nomic-embed-text:latest`).

## Global Constraints

- ALL code, comments, prompts, and commit messages in **ENGLISH**. User-facing
  chat strings (answers, refusal messages) in **POLISH**. Per agent task, a
  Polish learning note under `docs/learn/faza-3-<topic>.md` (concise but
  substantive study material). No AI-attribution footers in commits or PRs.
- Secrets never in the repo. BigQuery auth = ADC (already configured). Ollama =
  `http://localhost:11434`, no API keys.
- BigQuery free tier: guardrails dry-run gate (default max 1 GB) AND
  `maximum_bytes_billed` on every executed job. Unit tests must NOT touch live
  GCP or Ollama (mock/stub); live tests are `@pytest.mark.integration`
  (excluded by default via existing `pytest.ini`).
- GCP project `taxi-chat-data`, location US. Datasets: `raw` (blocked for
  chat), `staging`, `marts`.
- Python runs in the existing `.venv`: `.venv/bin/python`, `.venv/bin/pytest`.
  dbt stays Dockerized and is NOT touched this phase.
- New dependencies (added ONLY in Task 0 — no other task edits
  `requirements.txt`): `chromadb`, `sqlglot`, `langgraph`, `pyyaml`.
- Wave-1 tasks (1, 2, 3) must not modify any file outside their **Files** list.

---

## File Structure

```
genai/
├── __init__.py          # Task 0
├── config.py            # Task 0 — paths, URLs, model names, limits
├── types.py             # Task 0 — LLMError, SchemaContext, ValidationResult (THE contract)
├── llm_client.py        # Task 1
├── indexer.py           # Task 2
├── examples.yml         # Task 2 — Polish question → SQL few-shots
├── retriever.py         # Task 2
├── guardrails.py        # Task 3
├── nl2sql.py            # Task 4
├── pipeline.py          # Task 4 — LangGraph graph
└── ask.py               # Task 4 — CLI (python -m genai.ask)
tests/
├── test_genai_types.py        # Task 0
├── test_llm_client.py         # Task 1
├── test_indexer.py            # Task 2
├── test_retriever.py          # Task 2
├── test_guardrails.py         # Task 3
├── test_nl2sql.py             # Task 4
├── test_pipeline.py           # Task 4
└── test_e2e_integration.py    # Task 4 (marked integration; run live in Task 5)
docs/learn/
├── faza-3-llm-client.md       # Task 1 (Polish)
├── faza-3-rag-retriever.md    # Task 2 (Polish)
├── faza-3-guardrails.md       # Task 3 (Polish)
└── faza-3-langgraph-nl2sql.md # Task 4 (Polish)
```

---

## Task 0: Scaffold + shared contracts (in-session, BEFORE spawning agents)

**Files:**
- Create: `genai/__init__.py`, `genai/config.py`, `genai/types.py`
- Create: `tests/test_genai_types.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nothing.
- Produces: `genai.config` constants and `genai.types` dataclasses used by ALL
  later tasks (exact code below — later tasks import these, never redefine them).

- [ ] **Step 1: Write the failing contract test**

`tests/test_genai_types.py`:
```python
from genai.types import LLMError, SchemaContext, ValidationResult


def test_schema_context_holds_prompt_ready_strings():
    ctx = SchemaContext(tables=["Table marts.fct_trips: trips"], examples=["QUESTION: x\nSQL: y"])
    assert ctx.tables[0].startswith("Table ")
    assert len(ctx.examples) == 1


def test_validation_result_defaults():
    ok = ValidationResult(ok=True, sql="SELECT 1", reason=None, estimated_bytes=123)
    bad = ValidationResult(ok=False, sql="DROP TABLE x", reason="Tylko SELECT jest dozwolony.", estimated_bytes=None)
    assert ok.ok and not bad.ok
    assert isinstance(bad.reason, str)


def test_llm_error_is_exception():
    assert issubclass(LLMError, Exception)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_genai_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai'`

- [ ] **Step 3: Create the package**

`genai/__init__.py`:
```python
"""GenAI "chat with data" core: RAG + NL2SQL + guardrails (Faza 3)."""
```

`genai/config.py`:
```python
"""Central configuration for the genai package. No secrets here — auth is ADC."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"
DBT_MODELS_DIR = REPO_ROOT / "dbt" / "models"
EXAMPLES_PATH = Path(__file__).resolve().parent / "examples.yml"

OLLAMA_BASE_URL = "http://localhost:11434"
GENERATION_MODEL = "gemma4:latest"
EMBEDDING_MODEL = "nomic-embed-text:latest"

BQ_PROJECT = "taxi-chat-data"
BQ_LOCATION = "US"
ALLOWED_DATASETS = frozenset({"staging", "marts"})

MAX_SCAN_BYTES = 1_000_000_000  # 1 GB dry-run gate + maximum_bytes_billed
DEFAULT_LIMIT = 100             # appended to SELECTs missing a LIMIT
MAX_SQL_ATTEMPTS = 3            # 1 initial + 2 retries with error feedback
```

`genai/types.py`:
```python
"""Shared contracts between genai modules. Wave-1 tasks build against these."""
from dataclasses import dataclass


class LLMError(Exception):
    """Raised when the Ollama backend is unreachable or returns garbage."""


@dataclass
class SchemaContext:
    """RAG retrieval result, prompt-ready."""
    tables: list[str]    # formatted table/column descriptions
    examples: list[str]  # formatted "QUESTION: ...\nSQL: ..." pairs


@dataclass
class ValidationResult:
    """Guardrail verdict for one SQL statement."""
    ok: bool
    sql: str                        # possibly amended (e.g. LIMIT appended)
    reason: str | None              # Polish, user-facing / retry feedback
    estimated_bytes: int | None     # from the BigQuery dry-run
```

- [ ] **Step 4: Add dependencies and install**

Append to `requirements.txt`:
```
chromadb>=0.5
sqlglot>=25.0
langgraph>=0.2
pyyaml>=6.0
```

Run: `.venv/bin/pip install -r requirements.txt`
Expected: installs succeed (chromadb pulls several transitive deps — fine).

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_genai_types.py -v`
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add genai/ tests/test_genai_types.py requirements.txt
git commit -m "feat: genai package scaffold — shared contracts, config, deps (Faza 3 task 0)"
```

---

## Task 1: `llm_client.py` — Ollama HTTP client (wave 1, agent)

**Files:**
- Create: `genai/llm_client.py`
- Test: `tests/test_llm_client.py`
- Create: `docs/learn/faza-3-llm-client.md` (Polish learning note)

**Interfaces:**
- Consumes: `genai.config` (OLLAMA_BASE_URL, GENERATION_MODEL, EMBEDDING_MODEL),
  `genai.types.LLMError`.
- Produces (Task 2 and Task 4 rely on EXACTLY this):
  - `LLMClient(model: str = config.GENERATION_MODEL, base_url: str = config.OLLAMA_BASE_URL, timeout: int = 120)`
  - `LLMClient.generate(prompt: str, system: str | None = None) -> str` — raises `LLMError`
  - `LLMClient.embed(texts: list[str]) -> list[list[float]]` — uses
    `config.EMBEDDING_MODEL` regardless of `self.model`; raises `LLMError`

- [ ] **Step 1: Write the failing tests**

`tests/test_llm_client.py`:
```python
import pytest
import requests

from genai.llm_client import LLMClient
from genai.types import LLMError


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_generate_returns_response_text(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"response": "SELECT 1"})

    monkeypatch.setattr(requests, "post", fake_post)
    client = LLMClient()
    out = client.generate("write sql", system="you are a sql bot")
    assert out == "SELECT 1"
    assert captured["url"].endswith("/api/generate")
    assert captured["json"]["stream"] is False
    assert captured["json"]["system"] == "you are a sql bot"


def test_generate_raises_llm_error_when_ollama_down(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(LLMError, match="ollama serve"):
        LLMClient().generate("hi")


def test_generate_raises_llm_error_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({}, status=404))
    with pytest.raises(LLMError):
        LLMClient().generate("hi")


def test_embed_uses_embedding_model_and_returns_vectors(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    monkeypatch.setattr(requests, "post", fake_post)
    vectors = LLMClient().embed(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"].endswith("/api/embed")
    assert captured["json"]["model"] == "nomic-embed-text:latest"
    assert captured["json"]["input"] == ["a", "b"]


def test_embed_raises_llm_error_on_malformed_payload(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse({"weird": True}))
    with pytest.raises(LLMError):
        LLMClient().embed(["a"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.llm_client'`

- [ ] **Step 3: Implement `genai/llm_client.py`**

```python
"""Thin HTTP client for the local Ollama server. No framework, no magic."""
import requests

from genai import config
from genai.types import LLMError

_CONNECTION_HINT = (
    "Nie mogę połączyć się z Ollamą pod {url}. "
    "Uruchom `ollama serve` i sprawdź, że model jest zainstalowany (`ollama list`)."
)


class LLMClient:
    def __init__(
        self,
        model: str = config.GENERATION_MODEL,
        base_url: str = config.OLLAMA_BASE_URL,
        timeout: int = 120,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, prompt: str, system: str | None = None) -> str:
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        if system is not None:
            payload["system"] = system
        data = self._post("/api/generate", payload)
        if "response" not in data:
            raise LLMError(f"Unexpected Ollama /api/generate payload: {list(data)}")
        return data["response"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": config.EMBEDDING_MODEL, "input": texts}
        data = self._post("/api/embed", payload)
        if "embeddings" not in data:
            raise LLMError(f"Unexpected Ollama /api/embed payload: {list(data)}")
        return data["embeddings"]

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.ConnectionError as exc:
            raise LLMError(_CONNECTION_HINT.format(url=self.base_url)) from exc
        except requests.RequestException as exc:
            raise LLMError(f"Ollama request to {path} failed: {exc}") from exc
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_llm_client.py -v`
Expected: 5 PASS

- [ ] **Step 5: Write the Polish learning note**

`docs/learn/faza-3-llm-client.md` — cover (in Polish, your own words, ~60–90
lines): czym jest Ollama i jej HTTP API (`/api/generate` vs `/api/embed`,
`stream: false`), czemu embeddings robi inny model (nomic-embed-text) niż
generacja (gemma4), co to jest embedding (wektor znaczenia tekstu), czemu
opakowujemy błędy w domenowy `LLMError` z podpowiedzią zamiast puszczać
traceback `requests`, i czemu testy mockują `requests.post` (deterministyczne,
szybkie, bez zależności od działającej Ollamy).

- [ ] **Step 6: Commit**

```bash
git add genai/llm_client.py tests/test_llm_client.py docs/learn/faza-3-llm-client.md
git commit -m "feat: LLMClient — Ollama HTTP client for generation and embeddings"
```

---

## Task 2: RAG — `indexer.py` + `examples.yml` + `retriever.py` (wave 1, agent)

**Files:**
- Create: `genai/indexer.py`, `genai/examples.yml`, `genai/retriever.py`
- Test: `tests/test_indexer.py`, `tests/test_retriever.py`
- Create: `docs/learn/faza-3-rag-retriever.md` (Polish learning note)

**Interfaces:**
- Consumes: `genai.config` (CHROMA_DIR, DBT_MODELS_DIR, EXAMPLES_PATH),
  `genai.types.SchemaContext`. Type-only dependency on Task 1's
  `LLMClient.embed(texts: list[str]) -> list[list[float]]` — injected via
  constructor/parameter, ALWAYS mocked in unit tests (do NOT import
  `genai.llm_client` in tests; a tiny fake with an `embed` method suffices).
- Produces (Task 4 and Task 5 rely on EXACTLY this):
  - `indexer.build_index(chroma_dir: Path = config.CHROMA_DIR, embedder=None) -> dict`
    (returns `{"schema_docs": <count>, "examples": <count>}`; `embedder=None`
    constructs a real `LLMClient`). Runnable: `python -m genai.indexer`.
  - `Retriever(chroma_dir: Path = config.CHROMA_DIR, embedder=None)`
  - `Retriever.retrieve(question: str, k_schema: int = 4, k_examples: int = 3) -> SchemaContext`
- Chroma collection names (shared constant in `indexer.py`):
  `SCHEMA_COLLECTION = "schema_docs"`, `EXAMPLES_COLLECTION = "few_shot_examples"`.

- [ ] **Step 1: Write the failing indexer tests**

`tests/test_indexer.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_indexer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.indexer'`

- [ ] **Step 3: Implement `genai/indexer.py`**

```python
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
```

- [ ] **Step 4: Run indexer tests to verify they pass**

Run: `.venv/bin/pytest tests/test_indexer.py -v`
Expected: 4 PASS

- [ ] **Step 5: Write `genai/examples.yml` (curated few-shots, PL → BigQuery SQL)**

```yaml
# Few-shot examples for NL2SQL: Polish question -> correct BigQuery SQL.
# Curated by hand against the Faza 2 star schema. Indexed into Chroma by
# genai/indexer.py; the retriever surfaces the most similar ones per question.
examples:
  - question: "Ile było wszystkich przejazdów?"
    sql: "SELECT COUNT(*) AS trip_count FROM `taxi-chat-data.marts.fct_trips`"
  - question: "Jaka była średnia cena przejazdu?"
    sql: "SELECT ROUND(AVG(total_amount), 2) AS avg_total FROM `taxi-chat-data.marts.fct_trips`"
  - question: "Jaki był średni napiwek przy płatności kartą?"
    sql: |-
      SELECT ROUND(AVG(f.tip_amount), 2) AS avg_tip
      FROM `taxi-chat-data.marts.fct_trips` f
      JOIN `taxi-chat-data.marts.dim_payment` p ON f.payment_type = p.payment_type
      WHERE p.payment_desc = 'Credit card'
  - question: "Z których dzielnic startowało najwięcej kursów?"
    sql: |-
      SELECT l.borough, COUNT(*) AS trips
      FROM `taxi-chat-data.marts.fct_trips` f
      JOIN `taxi-chat-data.marts.dim_location` l ON f.pickup_location_id = l.location_id
      GROUP BY l.borough
      ORDER BY trips DESC
  - question: "Ile kursów było w weekendy, a ile w dni robocze?"
    sql: |-
      SELECT d.is_weekend, COUNT(*) AS trips
      FROM `taxi-chat-data.marts.fct_trips` f
      JOIN `taxi-chat-data.marts.dim_datetime` d ON f.pickup_date = d.date_key
      GROUP BY d.is_weekend
  - question: "Który dzień tygodnia miał najwięcej przejazdów?"
    sql: |-
      SELECT d.day_name, COUNT(*) AS trips
      FROM `taxi-chat-data.marts.fct_trips` f
      JOIN `taxi-chat-data.marts.dim_datetime` d ON f.pickup_date = d.date_key
      GROUP BY d.day_name
      ORDER BY trips DESC
      LIMIT 1
  - question: "Jaka jest średnia długość kursu w milach dla poszczególnych taryf?"
    sql: |-
      SELECT r.ratecode_desc, ROUND(AVG(f.trip_distance), 2) AS avg_distance
      FROM `taxi-chat-data.marts.fct_trips` f
      JOIN `taxi-chat-data.marts.dim_ratecode` r ON f.ratecode_id = r.ratecode_id
      GROUP BY r.ratecode_desc
      ORDER BY avg_distance DESC
  - question: "Pokaż 10 najdroższych przejazdów."
    sql: |-
      SELECT trip_key, pickup_datetime, trip_distance, total_amount
      FROM `taxi-chat-data.marts.fct_trips`
      ORDER BY total_amount DESC
      LIMIT 10
  - question: "Jak zmieniała się dzienna liczba kursów w czasie?"
    sql: |-
      SELECT pickup_date, COUNT(*) AS trips
      FROM `taxi-chat-data.marts.fct_trips`
      GROUP BY pickup_date
      ORDER BY pickup_date
  - question: "Jaki procent kursów opłacono gotówką?"
    sql: |-
      SELECT ROUND(100 * COUNTIF(p.payment_desc = 'Cash') / COUNT(*), 1) AS cash_pct
      FROM `taxi-chat-data.marts.fct_trips` f
      JOIN `taxi-chat-data.marts.dim_payment` p ON f.payment_type = p.payment_type
```

- [ ] **Step 6: Write the failing retriever tests**

`tests/test_retriever.py`:
```python
from pathlib import Path

import chromadb

from genai.indexer import SCHEMA_COLLECTION, EXAMPLES_COLLECTION
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
    example_texts = ["QUESTION: Ile było trip?\nSQL: SELECT 1", "QUESTION: platnosci?\nSQL: SELECT 2"]
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
```

- [ ] **Step 7: Run retriever tests to verify they fail**

Run: `.venv/bin/pytest tests/test_retriever.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.retriever'`

- [ ] **Step 8: Implement `genai/retriever.py`**

```python
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
```

- [ ] **Step 9: Run all Task 2 tests to verify they pass**

Run: `.venv/bin/pytest tests/test_indexer.py tests/test_retriever.py -v`
Expected: 6 PASS

- [ ] **Step 10: Write the Polish learning note**

`docs/learn/faza-3-rag-retriever.md` — cover (in Polish, ~80–120 lines): co to
jest RAG i czemu tu wystarczy "RAG na schemacie" (indeksujemy OPISY tabel, nie
dane); jak działa baza wektorowa (embedding → podobieństwo kosinusowe → top-k);
czym są kolekcje w Chromie i czemu trzymamy schemat oddzielnie od few-shotów;
rola few-shot examples przy słabszym modelu (gemma4) — pokazujemy wzorce
JOIN-ów zamiast liczyć na wiedzę modelu; czemu indeksacja to osobny krok
(`python -m genai.indexer`), a YAML-e dbt są jedynym źródłem prawdy; czemu w
testach wstrzykujemy FakeEmbedder (determinizm, brak Ollamy).

- [ ] **Step 11: Commit**

```bash
git add genai/indexer.py genai/examples.yml genai/retriever.py \
        tests/test_indexer.py tests/test_retriever.py docs/learn/faza-3-rag-retriever.md
git commit -m "feat: RAG layer — Chroma indexer over dbt docs, curated few-shots, retriever"
```

---

## Task 3: `guardrails.py` — SQL validation before execution (wave 1, agent)

**Files:**
- Create: `genai/guardrails.py`
- Test: `tests/test_guardrails.py`
- Create: `docs/learn/faza-3-guardrails.md` (Polish learning note)

**Interfaces:**
- Consumes: `genai.config` (ALLOWED_DATASETS, BQ_PROJECT, MAX_SCAN_BYTES,
  DEFAULT_LIMIT), `genai.types.ValidationResult`, `google.cloud.bigquery`
  (already in requirements), `sqlglot`. NO imports from `llm_client`/`retriever`.
- Produces (Task 4 relies on EXACTLY this):
  - `validate(sql: str, *, max_bytes: int = config.MAX_SCAN_BYTES, bq_client=None) -> ValidationResult`
    — `bq_client=None` constructs `bigquery.Client(project=config.BQ_PROJECT)`;
    tests pass a stub. Never raises for bad SQL — always returns a
    `ValidationResult` (raising is reserved for infrastructure failures).

- [ ] **Step 1: Write the failing tests**

`tests/test_guardrails.py`:
```python
import pytest

from genai.guardrails import validate


class FakeDryRunJob:
    def __init__(self, total_bytes_processed):
        self.total_bytes_processed = total_bytes_processed


class FakeBQClient:
    def __init__(self, dry_run_bytes=1_000):
        self.dry_run_bytes = dry_run_bytes
        self.queries = []

    def query(self, sql, job_config=None):
        assert job_config.dry_run is True
        self.queries.append(sql)
        return FakeDryRunJob(self.dry_run_bytes)


BQ = FakeBQClient


def test_rejects_unparseable_sql():
    result = validate("SELEKT gunk FROM", bq_client=BQ())
    assert not result.ok
    assert result.reason is not None


def test_rejects_non_select_statements():
    for sql in [
        "DELETE FROM `taxi-chat-data.marts.fct_trips` WHERE true",
        "DROP TABLE `taxi-chat-data.marts.fct_trips`",
        "UPDATE `taxi-chat-data.marts.fct_trips` SET fare_amount = 0 WHERE true",
        "INSERT INTO `taxi-chat-data.marts.fct_trips` (trip_key) VALUES ('x')",
    ]:
        result = validate(sql, bq_client=BQ())
        assert not result.ok, sql
        assert "SELECT" in result.reason


def test_rejects_multiple_statements():
    result = validate("SELECT 1; SELECT 2", bq_client=BQ())
    assert not result.ok


def test_rejects_tables_outside_allowlist():
    result = validate("SELECT * FROM `taxi-chat-data.raw.trips` LIMIT 5", bq_client=BQ())
    assert not result.ok
    assert "raw.trips" in result.reason


def test_rejects_unqualified_tables():
    result = validate("SELECT * FROM fct_trips LIMIT 5", bq_client=BQ())
    assert not result.ok


def test_accepts_allowlisted_table_and_keeps_existing_limit():
    sql = "SELECT trip_key FROM `taxi-chat-data.marts.fct_trips` LIMIT 7"
    result = validate(sql, bq_client=BQ())
    assert result.ok
    assert "LIMIT 7" in result.sql


def test_appends_default_limit_when_missing():
    result = validate("SELECT trip_key FROM `taxi-chat-data.marts.fct_trips`", bq_client=BQ())
    assert result.ok
    assert "LIMIT 100" in result.sql


def test_allows_cte_names_that_are_not_real_tables():
    sql = (
        "WITH daily AS (SELECT pickup_date, COUNT(*) AS trips "
        "FROM `taxi-chat-data.marts.fct_trips` GROUP BY pickup_date) "
        "SELECT * FROM daily ORDER BY trips DESC"
    )
    result = validate(sql, bq_client=BQ())
    assert result.ok


def test_rejects_queries_over_scan_budget():
    client = BQ(dry_run_bytes=5_000_000_000)
    result = validate(
        "SELECT trip_key FROM `taxi-chat-data.marts.fct_trips` LIMIT 5",
        max_bytes=1_000_000_000,
        bq_client=client,
    )
    assert not result.ok
    assert result.estimated_bytes == 5_000_000_000


def test_reports_estimated_bytes_on_success():
    client = BQ(dry_run_bytes=42)
    result = validate("SELECT 1 FROM `taxi-chat-data.marts.dim_payment` LIMIT 1", bq_client=client)
    assert result.ok
    assert result.estimated_bytes == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_guardrails.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.guardrails'`

- [ ] **Step 3: Implement `genai/guardrails.py`**

```python
"""SQL guardrails: validate generated SQL BEFORE it touches real data.

Order of gates:
1. Parse (sqlglot, BigQuery dialect) — reject unparseable input.
2. Exactly one statement, and it must be a plain SELECT (CTEs allowed).
3. Every referenced table must live in an allowlisted dataset (staging/marts).
4. Enforce a LIMIT (append config.DEFAULT_LIMIT when missing).
5. BigQuery dry-run — reject when the estimated scan exceeds max_bytes.

Reasons are in Polish: they go straight to the user (or back to the model as
retry feedback).
"""
import sqlglot
from sqlglot import exp

from genai import config
from genai.types import ValidationResult


def _reject(sql: str, reason: str, estimated_bytes: int | None = None) -> ValidationResult:
    return ValidationResult(ok=False, sql=sql, reason=reason, estimated_bytes=estimated_bytes)


def validate(sql: str, *, max_bytes: int = config.MAX_SCAN_BYTES, bq_client=None) -> ValidationResult:
    try:
        statements = sqlglot.parse(sql, read="bigquery")
    except sqlglot.errors.ParseError as exc:
        return _reject(sql, f"Nie udało się sparsować SQL: {exc}")

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return _reject(sql, "Dozwolone jest dokładnie jedno zapytanie SQL.")

    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union)):
        return _reject(sql, "Dozwolone są wyłącznie zapytania SELECT (odczyt danych).")

    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if table.name in cte_names and not table.db:
            continue  # reference to a CTE, not a real table
        if table.catalog and table.catalog != config.BQ_PROJECT:
            return _reject(sql, f"Tabela spoza projektu: {table.sql(dialect='bigquery')}.")
        if table.db not in config.ALLOWED_DATASETS:
            shown = f"{table.db}.{table.name}" if table.db else table.name
            return _reject(
                sql,
                f"Tabela {shown} jest poza dozwolonymi zbiorami danych "
                f"({', '.join(sorted(config.ALLOWED_DATASETS))}).",
            )

    if not statement.args.get("limit"):
        statement = statement.limit(config.DEFAULT_LIMIT)
    final_sql = statement.sql(dialect="bigquery")

    if bq_client is None:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=config.BQ_PROJECT)
    from google.cloud.bigquery import QueryJobConfig

    job = bq_client.query(final_sql, job_config=QueryJobConfig(dry_run=True, use_query_cache=False))
    estimated = job.total_bytes_processed
    if estimated is not None and estimated > max_bytes:
        return _reject(
            final_sql,
            f"Zapytanie przeskanowałoby ~{estimated / 1e9:.2f} GB "
            f"(limit: {max_bytes / 1e9:.2f} GB). Doprecyzuj pytanie.",
            estimated_bytes=estimated,
        )

    return ValidationResult(ok=True, sql=final_sql, reason=None, estimated_bytes=estimated)
```

Note for the implementer: the `FakeBQClient` in the tests builds a real
`QueryJobConfig`? No — `validate` builds the job config itself and the fake
only asserts `job_config.dry_run is True`. `google.cloud.bigquery` is already
installed (Faza 1), so the import inside `validate` works in unit tests too.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_guardrails.py -v`
Expected: 10 PASS

- [ ] **Step 5: Write the Polish learning note**

`docs/learn/faza-3-guardrails.md` — cover (in Polish, ~80–120 lines): czemu
walidujemy SQL PRZED wykonaniem (prompt injection, halucynacje modelu, koszty);
parsowanie do AST przez sqlglot zamiast regexów (czemu regex `^SELECT` to za
mało — np. `SELECT ...; DROP ...`); allowlista datasetów jako least privilege;
wymuszony LIMIT; czym jest dry-run w BigQuery (darmowa wycena skanu) i jak
chroni free tier; wzorzec "zwróć werdykt, nie rzucaj wyjątkiem" (ValidationResult)
i czemu komunikaty są po polsku (idą do użytkownika i jako feedback do retry).

- [ ] **Step 6: Commit**

```bash
git add genai/guardrails.py tests/test_guardrails.py docs/learn/faza-3-guardrails.md
git commit -m "feat: SQL guardrails — sqlglot AST gates, dataset allowlist, LIMIT, BQ dry-run"
```

---

## Task 4: `nl2sql.py` + `pipeline.py` (LangGraph) + `ask.py` CLI (wave 2, agent; depends on Tasks 1–3)

**Files:**
- Create: `genai/nl2sql.py`, `genai/pipeline.py`, `genai/ask.py`
- Test: `tests/test_nl2sql.py`, `tests/test_pipeline.py`, `tests/test_e2e_integration.py`
- Create: `docs/learn/faza-3-langgraph-nl2sql.md` (Polish learning note)

**Interfaces:**
- Consumes (from Tasks 0–3, exact signatures):
  - `LLMClient.generate(prompt: str, system: str | None = None) -> str`
  - `Retriever.retrieve(question: str, k_schema: int = 4, k_examples: int = 3) -> SchemaContext`
  - `guardrails.validate(sql: str, *, max_bytes=..., bq_client=None) -> ValidationResult`
  - `config.MAX_SQL_ATTEMPTS`, `config.MAX_SCAN_BYTES`, `config.BQ_PROJECT`
- Produces:
  - `nl2sql.generate_sql(llm, question: str, context: SchemaContext, error_feedback: str | None = None) -> str`
  - `nl2sql.extract_sql(response: str) -> str`
  - `pipeline.build_pipeline(llm=None, retriever=None, validate_fn=None, bq_client=None)`
    → compiled LangGraph app; `pipeline.ask(question: str) -> dict` (final state)
  - CLI: `python -m genai.ask "pytanie"`

- [x] **Step 1: Write the failing nl2sql tests**

`tests/test_nl2sql.py`:
```python
from genai.nl2sql import build_prompt, extract_sql, generate_sql
from genai.types import SchemaContext

CTX = SchemaContext(
    tables=["Table marts.fct_trips: trips fact"],
    examples=["QUESTION: Ile było przejazdów?\nSQL: SELECT COUNT(*) FROM `taxi-chat-data.marts.fct_trips`"],
)


def test_build_prompt_contains_question_context_and_examples():
    prompt = build_prompt("Ile było kursów?", CTX)
    assert "Ile było kursów?" in prompt
    assert "Table marts.fct_trips" in prompt
    assert "QUESTION: Ile było przejazdów?" in prompt


def test_build_prompt_includes_error_feedback_on_retry():
    prompt = build_prompt("Ile?", CTX, error_feedback="Tabela raw.trips jest poza allowlistą")
    assert "raw.trips" in prompt
    assert "poprzednia próba" in prompt.lower() or "previous attempt" in prompt.lower()


def test_extract_sql_from_fenced_block():
    text = "Sure!\n```sql\nSELECT 1\n```\nHope it helps."
    assert extract_sql(text) == "SELECT 1"


def test_extract_sql_from_plain_fence_and_strips_semicolon():
    assert extract_sql("```\nSELECT 2;\n```") == "SELECT 2"


def test_extract_sql_falls_back_to_raw_text():
    assert extract_sql("  SELECT 3  ") == "SELECT 3"


def test_generate_sql_calls_llm_and_extracts():
    class FakeLLM:
        def generate(self, prompt, system=None):
            self.prompt = prompt
            self.system = system
            return "```sql\nSELECT COUNT(*) FROM `taxi-chat-data.marts.fct_trips`\n```"

    llm = FakeLLM()
    sql = generate_sql(llm, "Ile było kursów?", CTX)
    assert sql == "SELECT COUNT(*) FROM `taxi-chat-data.marts.fct_trips`"
    assert llm.system is not None and "BigQuery" in llm.system
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_nl2sql.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.nl2sql'`

- [x] **Step 3: Implement `genai/nl2sql.py`**

```python
"""Prompt assembly and SQL extraction for the NL2SQL step."""
import re

from genai.types import SchemaContext

SYSTEM_PROMPT = (
    "You are an expert BigQuery SQL generator for an NYC taxi data warehouse. "
    "Return exactly ONE standard-SQL SELECT statement inside a ```sql fence. "
    "Use ONLY the tables and columns provided in the context, always fully "
    "qualified as `taxi-chat-data.<dataset>.<table>`. Never modify data. "
    "The user's question is in Polish."
)

_PROMPT_TEMPLATE = """Schema context:
{tables}

Similar solved examples:
{examples}

{feedback}Question (Polish): {question}

Reply with the SQL only."""


def build_prompt(question: str, context: SchemaContext, error_feedback: str | None = None) -> str:
    feedback = ""
    if error_feedback:
        feedback = (
            "IMPORTANT — previous attempt was rejected (poprzednia próba odrzucona): "
            f"{error_feedback}\nFix the SQL accordingly.\n\n"
        )
    return _PROMPT_TEMPLATE.format(
        tables="\n\n".join(context.tables),
        examples="\n\n".join(context.examples),
        feedback=feedback,
        question=question,
    )


def extract_sql(response: str) -> str:
    for pattern in (r"```sql\s*(.+?)```", r"```\s*(.+?)```"):
        match = re.search(pattern, response, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(";")
    return response.strip().rstrip(";")


def generate_sql(llm, question: str, context: SchemaContext, error_feedback: str | None = None) -> str:
    response = llm.generate(build_prompt(question, context, error_feedback), system=SYSTEM_PROMPT)
    return extract_sql(response)
```

- [x] **Step 4: Run nl2sql tests to verify they pass**

Run: `.venv/bin/pytest tests/test_nl2sql.py -v`
Expected: 6 PASS

- [x] **Step 5: Commit nl2sql**

```bash
git add genai/nl2sql.py tests/test_nl2sql.py
git commit -m "feat: NL2SQL prompt assembly and SQL extraction"
```

- [x] **Step 6: Write the failing pipeline tests**

`tests/test_pipeline.py`:
```python
from genai.pipeline import build_pipeline
from genai.types import SchemaContext, ValidationResult

CTX = SchemaContext(tables=["Table marts.fct_trips: trips"], examples=["QUESTION: q\nSQL: s"])
GOOD_SQL = "SELECT COUNT(*) AS c FROM `taxi-chat-data.marts.fct_trips` LIMIT 100"


class FakeRetriever:
    def retrieve(self, question, k_schema=4, k_examples=3):
        return CTX


class FakeLLM:
    """Returns queued generate() responses, then keeps repeating the last one."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate(self, prompt, system=None):
        self.prompts.append(prompt)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


class FakeRow:
    def __init__(self, data):
        self._data = data

    def items(self):
        return self._data.items()

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()


class FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows
        self.total_bytes_processed = 512

    def result(self):
        return self._rows


class FakeBQClient:
    def __init__(self):
        self.executed = []

    def query(self, sql, job_config=None):
        assert job_config.maximum_bytes_billed is not None
        self.executed.append(sql)
        return FakeQueryJob([FakeRow({"c": 3066766})])


def _validate_ok(sql, **kwargs):
    return ValidationResult(ok=True, sql=sql, reason=None, estimated_bytes=512)


def test_happy_path_retrieve_generate_validate_execute_summarize():
    llm = FakeLLM([f"```sql\n{GOOD_SQL}\n```", "W hurtowni są 3 066 766 przejazdy."])
    bq = FakeBQClient()
    app = build_pipeline(llm=llm, retriever=FakeRetriever(), validate_fn=_validate_ok, bq_client=bq)
    state = app.invoke({"question": "Ile było przejazdów?"})
    assert state["refused"] is False
    assert state["rows"] == [{"c": 3066766}]
    assert state["answer"] == "W hurtowni są 3 066 766 przejazdy."
    assert bq.executed == [GOOD_SQL]


def test_validation_failure_retries_with_feedback_then_succeeds():
    calls = {"n": 0}

    def flaky_validate(sql, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return ValidationResult(ok=False, sql=sql, reason="Brak LIMIT", estimated_bytes=None)
        return ValidationResult(ok=True, sql=sql, reason=None, estimated_bytes=1)

    llm = FakeLLM([f"```sql\n{GOOD_SQL}\n```", f"```sql\n{GOOD_SQL}\n```", "Odpowiedź."])
    app = build_pipeline(llm=llm, retriever=FakeRetriever(), validate_fn=flaky_validate, bq_client=FakeBQClient())
    state = app.invoke({"question": "Ile?"})
    assert state["refused"] is False
    assert calls["n"] == 2
    assert any("Brak LIMIT" in p for p in llm.prompts)  # feedback reached the model


def test_refuses_after_exhausting_attempts():
    def always_reject(sql, **kwargs):
        return ValidationResult(ok=False, sql=sql, reason="Tylko SELECT.", estimated_bytes=None)

    llm = FakeLLM(["```sql\nDROP TABLE x\n```"])
    app = build_pipeline(llm=llm, retriever=FakeRetriever(), validate_fn=always_reject, bq_client=FakeBQClient())
    state = app.invoke({"question": "Usuń dane"})
    assert state["refused"] is True
    assert "Tylko SELECT." in state["answer"]
    assert state["rows"] == []
```

- [x] **Step 7: Run pipeline tests to verify they fail**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'genai.pipeline'`

- [x] **Step 8: Implement `genai/pipeline.py`**

```python
"""LangGraph pipeline: retrieve → generate_sql → validate ⇄ retry → execute → summarize.

The graph earns its keep through the validate→generate_sql back-edge: on a
guardrail rejection the model gets the Polish reason as feedback and tries
again (config.MAX_SQL_ATTEMPTS total attempts).
"""
from typing import TypedDict

from langgraph.graph import END, StateGraph

from genai import config, guardrails, nl2sql
from genai.types import SchemaContext, ValidationResult

SUMMARY_SYSTEM = (
    "You are a helpful data analyst. Answer in POLISH, briefly and concretely, "
    "based ONLY on the provided query result rows."
)

REFUSAL_TEMPLATE = (
    "Nie umiem bezpiecznie odpowiedzieć na to pytanie. "
    "Ostatni powód odrzucenia: {reason}"
)


class AskState(TypedDict, total=False):
    question: str
    context: SchemaContext
    sql: str
    validation: ValidationResult
    attempts: int
    error_feedback: str
    rows: list[dict]
    scanned_bytes: int
    answer: str
    refused: bool


def build_pipeline(llm=None, retriever=None, validate_fn=None, bq_client=None):
    if llm is None:
        from genai.llm_client import LLMClient
        llm = LLMClient()
    if retriever is None:
        from genai.retriever import Retriever
        retriever = Retriever(embedder=llm)
    if validate_fn is None:
        validate_fn = guardrails.validate
    if bq_client is None:
        from google.cloud import bigquery
        bq_client = bigquery.Client(project=config.BQ_PROJECT)

    def retrieve(state: AskState) -> AskState:
        return {"context": retriever.retrieve(state["question"]), "attempts": 0,
                "refused": False, "rows": []}

    def generate_sql(state: AskState) -> AskState:
        sql = nl2sql.generate_sql(
            llm, state["question"], state["context"], state.get("error_feedback")
        )
        return {"sql": sql, "attempts": state["attempts"] + 1}

    def validate(state: AskState) -> AskState:
        result = validate_fn(state["sql"])
        updates: AskState = {"validation": result}
        if not result.ok:
            updates["error_feedback"] = result.reason
        return updates

    def route_after_validate(state: AskState) -> str:
        if state["validation"].ok:
            return "execute"
        if state["attempts"] >= config.MAX_SQL_ATTEMPTS:
            return "refuse"
        return "generate_sql"

    def execute(state: AskState) -> AskState:
        from google.cloud.bigquery import QueryJobConfig
        job = bq_client.query(
            state["validation"].sql,
            job_config=QueryJobConfig(maximum_bytes_billed=config.MAX_SCAN_BYTES),
        )
        rows = [dict(row.items()) for row in job.result()]
        return {"rows": rows, "scanned_bytes": job.total_bytes_processed or 0,
                "sql": state["validation"].sql}

    def summarize(state: AskState) -> AskState:
        prompt = (
            f"Question (Polish): {state['question']}\n"
            f"SQL used: {state['sql']}\n"
            f"Result rows (max 20 shown): {state['rows'][:20]}\n"
            "Answer the question in Polish."
        )
        return {"answer": llm.generate(prompt, system=SUMMARY_SYSTEM)}

    def refuse(state: AskState) -> AskState:
        reason = state["validation"].reason or "nieznany"
        return {"refused": True, "answer": REFUSAL_TEMPLATE.format(reason=reason)}

    graph = StateGraph(AskState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate", validate)
    graph.add_node("execute", execute)
    graph.add_node("summarize", summarize)
    graph.add_node("refuse", refuse)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "generate_sql")
    graph.add_edge("generate_sql", "validate")
    graph.add_conditional_edges("validate", route_after_validate,
                                {"execute": "execute", "generate_sql": "generate_sql",
                                 "refuse": "refuse"})
    graph.add_edge("execute", "summarize")
    graph.add_edge("summarize", END)
    graph.add_edge("refuse", END)
    return graph.compile()


def ask(question: str) -> dict:
    """Convenience wrapper used by the CLI: real components, one question."""
    app = build_pipeline()
    return app.invoke({"question": question})
```

- [x] **Step 9: Run pipeline tests to verify they pass**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Expected: 3 PASS

- [x] **Step 10: Implement `genai/ask.py` (CLI)**

```python
"""Single-shot CLI: python -m genai.ask "Ile było przejazdów?" """
import argparse
import sys

from genai.pipeline import ask
from genai.types import LLMError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chat with the NYC taxi warehouse (Polish).")
    parser.add_argument("question", help="Pytanie po polsku, w cudzysłowie.")
    args = parser.parse_args(argv)

    try:
        state = ask(args.question)
    except LLMError as exc:
        print(f"BŁĄD: {exc}", file=sys.stderr)
        return 1

    print(f"\nODPOWIEDŹ:\n{state['answer']}\n")
    if not state.get("refused"):
        print(f"UŻYTY SQL:\n{state['sql']}\n")
        print(f"ZESKANOWANO: {state.get('scanned_bytes', 0) / 1e9:.4f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Manual check: `.venv/bin/python -m genai.ask --help` prints usage and exits 0.

- [x] **Step 11: Write the integration e2e test (marked, NOT run in CI)**

`tests/test_e2e_integration.py`:
```python
"""Live end-to-end tests: require running Ollama, ADC, and a built Chroma index
(python -m genai.indexer). Run manually: .venv/bin/pytest -m integration -v"""
import pytest

from genai.pipeline import ask

pytestmark = pytest.mark.integration


def test_simple_count_question_returns_polish_answer():
    state = ask("Ile było wszystkich przejazdów?")
    assert state["refused"] is False
    assert state["rows"], "expected at least one result row"
    assert state["answer"].strip()
    assert "SELECT" in state["sql"].upper()


def test_join_question_uses_dimension_table():
    state = ask("Z której dzielnicy startowało najwięcej kursów?")
    assert state["refused"] is False
    assert "dim_location" in state["sql"]


def test_destructive_question_is_refused():
    state = ask("Usuń wszystkie przejazdy z bazy danych")
    assert state["refused"] is True
    assert state["rows"] == []
```

Run: `.venv/bin/pytest tests/test_e2e_integration.py -v`
Expected: `3 deselected` (integration excluded by default) — the live run
happens in Task 5.

- [x] **Step 12: Run the full unit suite**

Run: `.venv/bin/pytest -v`
Expected: all unit tests PASS (Tasks 0–4), integration deselected.

- [x] **Step 13: Write the Polish learning note**

`docs/learn/faza-3-langgraph-nl2sql.md` — cover (in Polish, ~80–120 lines):
czym jest LangGraph i czym różni się od LangChain (graf stanów z cyklami vs
liniowe chainy); jak wygląda nasz graf (węzły, krawędź warunkowa, pętla retry
z feedbackiem błędu); czemu stan to TypedDict i co LangGraph robi z częściowymi
update'ami; anatomia prompta NL2SQL (system prompt, kontekst RAG, few-shoty,
feedback z poprzedniej próby); czemu wyciągamy SQL regexem z fence'a i
zdejmujemy średnik; wzorzec dependency injection w build_pipeline (testy z
fake'ami bez Ollamy/BQ).

- [x] **Step 14: Commit**

```bash
git add genai/pipeline.py genai/ask.py tests/test_pipeline.py \
        tests/test_e2e_integration.py docs/learn/faza-3-langgraph-nl2sql.md
git commit -m "feat: LangGraph ask pipeline with guardrail retry cycle + CLI"
```

---

## Task 5: Index, live e2e, docs, verification (in-session, after Task 4 merges)

**Files:**
- Modify: `README.md` (add Faza 3 to the offer map / usage section)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Build the index**

Run: `.venv/bin/python -m genai.indexer`
Expected: `schema_docs: 6 documents indexed` (stg_trips + 4 dims + fct_trips)
and `few_shot_examples: 10 documents indexed`.

- [ ] **Step 2: Run the live integration suite**

Preconditions: `ollama list` shows gemma4 + nomic-embed-text; ADC valid.
Run: `.venv/bin/pytest -m integration -v`
Expected: 3 PASS. If NL2SQL quality makes an assertion flaky, note WHICH
question failed and how — that is Faza 6 evaluation material, not something to
paper over.

- [ ] **Step 3: Manual demo (evidence for the PR body)**

Run: `.venv/bin/python -m genai.ask "Jaki był średni napiwek przy płatności kartą?"`
Expected: Polish answer + SQL + scanned GB. Copy the output into the PR body.

Run: `.venv/bin/python -m genai.ask "Usuń wszystkie dane"`
Expected: refusal with a Polish reason, exit code 0, no SQL executed.

- [ ] **Step 4: Update README**

Add a "Faza 3: chat with data" section: what works (`python -m genai.indexer`,
`python -m genai.ask "..."`), the guardrail list, and extend the offer-map
table rows (NL2SQL + risk mitigation → `genai/guardrails.py` + pipeline retry;
RAG + vector DB → `genai/indexer.py`/`retriever.py` + Chroma).

- [ ] **Step 5: Full suite + commit + PR**

Run: `.venv/bin/pytest` → all green.
```bash
git add README.md
git commit -m "docs: README — Faza 3 chat-with-data usage and offer map"
git push -u origin feat/faza-3-genai-chat
gh pr create --title "Faza 3: GenAI chat with data (RAG + NL2SQL + guardrails)" \
  --body "$(cat <<'EOF'
## What
RAG (Chroma + nomic-embed) + NL2SQL (gemma4 via Ollama) + guardrails
(sqlglot AST gates, dataset allowlist, enforced LIMIT, BQ dry-run) wired as a
LangGraph pipeline with a validate→regenerate retry cycle. CLI:
`python -m genai.ask "pytanie po polsku"`.

## Evidence
(paste the Task 5 demo outputs here: happy-path answer + refusal)

## Tests
- unit: `pytest` all green (no live services)
- live: `pytest -m integration -v` — 3 passed
EOF
)"
```

---

## Harness execution notes (operator)

- Task 0 and Task 5 run in the operator session on `feat/faza-3-genai-chat`.
- Wave 1: 3 agents, tasks `faza-3-task-1`, `faza-3-task-2`, `faza-3-task-3`
  (specs in `docs/tasks/`), branched off `feat/faza-3-genai-chat` AFTER Task 0
  is committed. No shared files between them.
- Wave 2: 1 agent, `faza-3-task-4`, with
  `set-depends-on.sh <agent>:committed` on all three wave-1 agents; its
  worktree must include merged wave-1 work (rebase after their PRs land).
- Ollama is host-global and handles concurrent requests fine; BigQuery is
  touched only by dry-runs and small SELECTs — no cross-agent contention this
  phase.
