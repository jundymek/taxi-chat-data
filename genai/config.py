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
