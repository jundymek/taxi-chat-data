"""Central configuration for the genai package. No secrets here — auth is ADC."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"
DBT_MODELS_DIR = REPO_ROOT / "dbt" / "models"
EXAMPLES_PATH = Path(__file__).resolve().parent / "examples.yml"

# Ollama always runs on the host, never in a container. Natively that is
# localhost; from inside a container it is host.docker.internal, which compose
# passes in via OLLAMA_BASE_URL. The default keeps the native dev loop unchanged.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GENERATION_MODEL = "gemma4:latest"
EMBEDDING_MODEL = "nomic-embed-text:latest"

# NL2SQL wants the single most-likely SQL, not creative variety. Temperature 0
# plus a fixed seed makes generation deterministic, which is what turns the eval
# score into a metric someone else can reproduce instead of a per-run lottery.
# Ollama's own defaults (temperature 0.8) would reintroduce that variance.
GENERATION_TEMPERATURE = 0.0
GENERATION_SEED = 42

# Per-request Ollama timeout. A cold model (or the first request after Ollama
# swaps a model into VRAM) can take well over a minute, and NL2SQL may retry up
# to MAX_SQL_ATTEMPTS times — so the old 120s was tight enough to surface as a
# connection error on a single slow question. Overridable for slower hosts.
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))

BQ_PROJECT = "taxi-chat-data"
BQ_LOCATION = "US"
ALLOWED_DATASETS = frozenset({"staging", "marts"})

MAX_SCAN_BYTES = 1_000_000_000  # 1 GB dry-run gate + maximum_bytes_billed
DEFAULT_LIMIT = 100             # appended to SELECTs missing a LIMIT
MAX_SQL_ATTEMPTS = 3            # 1 initial + 2 retries with error feedback
