# Faza 0 + Faza 1: Setup i Batch Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Postawić szkielet projektu (repo, Docker, GCP, env) i pierwszy działający przepływ batch: plik Parquet NYC Taxi → bucket GCS (Data Lake, warstwa raw) → tabela `raw.trips` w BigQuery.

**Architecture:** Projekt data-engineeringowy uczący warstw z oferty pracy. Ta faza tworzy fundament i jedną, w pełni działającą drogę danych (batch). Streaming, hurtownia (dbt) i GenAI to kolejne fazy — patrz `docs/DESIGN.md`. Load do BQ jest surowy (bez transformacji); transformacje robi dbt w Fazie 2.

**Tech Stack:** Python 3.14, Google Cloud SDK (`gcloud`, `bq`, `gsutil`), biblioteki `google-cloud-storage` + `google-cloud-bigquery` + `pandas` + `pyarrow`, Docker (dla Airflow w późniejszych fazach), pytest.

## Global Constraints

Skopiowane wprost z `docs/DESIGN.md`:

- **Zero kosztów LLM** — wszystkie modele lokalnie przez Ollama. Ta faza nie dotyka LLM.
- **BigQuery tylko w ramach free tier** — 1 TB zapytań/mies gratis, 10 GB storage gratis. Wycinek danych **mały świadomie**: 1–2 miesiące taxi, nie lata.
- **Sekrety NIGDY w repo** — klucz GCP i configi przez `.env` (w `.gitignore`). Uwierzytelnianie preferowane przez `gcloud auth application-default login` (ADC), nie plik klucza serwisowego.
- **Region GCP:** `europe-central2` (Warszawa) lub `US` — patrz uwaga w Task 3 (dataset publiczny taxi i free tier). Ustalone: **`US` multi-region** dla spójności z publicznymi datasetami BQ.
- **Nazewnictwo datasetów BQ:** `raw`, `staging`, `marts` (medallion). Ta faza tworzy tylko `raw`.
- **Python:** `python3` (nie `python`), zależności w `.venv`.

---

## Warunki wstępne (RĘCZNE — wymagają Twojej akcji, plan ich nie zrobi)

Te kroki wymagają Twojego konta Google i logowania w przeglądarce — agent nie
może ich wykonać za Ciebie. Zrób je przed Task 3.

**P1. Konto GCP + projekt + billing:**
- Załóż/zaloguj konto na https://console.cloud.google.com
- Utwórz nowy projekt (zapamiętaj `PROJECT_ID`)
- Włącz billing (free tier wymaga karty, ale nie obciąża w ramach limitów;
  możesz też użyć darmowych kredytów $300 dla nowych kont)
- Włącz API: BigQuery API, Cloud Storage API (konsola → APIs & Services)

**P2. Instalacja Google Cloud SDK (gcloud NIE jest zainstalowany):**
```bash
brew install --cask google-cloud-sdk
```
Po instalacji zweryfikuj: `gcloud --version` (powinno wypisać wersje komponentów).

**P3. Logowanie (ADC — Application Default Credentials, bez pliku klucza):**
```bash
gcloud auth login
gcloud config set project TWOJ_PROJECT_ID
gcloud auth application-default login
```
ADC zapisze credentiale lokalnie (`~/.config/gcloud/`) — kod je podejmie
automatycznie, bez klucza serwisowego w repo. To najbezpieczniejsza droga na dev.

---

## File Structure

- `.gitignore` — ignoruje `.env`, `.venv/`, credentiale, `__pycache__`, dane
- `.env.example` — szablon zmiennych (PROJECT_ID, bucket, dataset, ścieżki)
- `README.md` — opis projektu + mapa na wymagania oferty + jak uruchomić
- `requirements.txt` — zależności Pythona
- `ingestion/__init__.py`
- `ingestion/config.py` — wczytanie configu z env (jedno źródło prawdy)
- `ingestion/download.py` — pobranie pliku Parquet NYC Taxi na dysk
- `ingestion/batch_load.py` — Parquet (dysk) → GCS → BigQuery `raw.trips`
- `tests/__init__.py`
- `tests/test_config.py`
- `tests/test_download.py`
- `tests/test_batch_load.py`

Podział: `download` (pobranie źródła) i `batch_load` (GCS + BQ) osobno — różne
odpowiedzialności, osobno testowalne. `config` centralizuje env, żeby nie
rozsypywać `os.getenv` po modułach.

---

## Task 1: Szkielet repo (gitignore, env, README, venv, zależności)

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `README.md`
- Create: `ingestion/__init__.py` (pusty)
- Create: `tests/__init__.py` (pusty)

**Interfaces:**
- Consumes: nic (pierwszy task)
- Produces: `.venv` z zależnościami, `.env.example` z kluczami: `GCP_PROJECT_ID`,
  `GCS_BUCKET`, `BQ_DATASET_RAW`, `BQ_LOCATION`, `TAXI_DATA_DIR`, `TAXI_MONTH`

- [ ] **Step 1: Utwórz `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.env
.env.local
# GCP credentials — NIGDY w repo
gcp_key.json
*-key.json
credentials.json
# Dane (nie wersjonujemy Parquetów)
data/
*.parquet
# IDE
.vscode/
.idea/
.DS_Store
```

- [ ] **Step 2: Utwórz `.env.example`**

```bash
# GCP
GCP_PROJECT_ID=twoj-project-id
GCS_BUCKET=twoj-project-id-taxi-lake
BQ_DATASET_RAW=raw
BQ_LOCATION=US

# Dane
TAXI_DATA_DIR=./data
# Format: yellow_tripdata_YYYY-MM (np. jeden miesiąc, mały wycinek pod free tier)
TAXI_MONTH=2023-01
```

- [ ] **Step 3: Utwórz `requirements.txt`**

```
google-cloud-storage>=2.14
google-cloud-bigquery>=3.17
pandas>=2.2
pyarrow>=15.0
requests>=2.31
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 4: Utwórz `README.md`**

```markdown
# taxi-chat-data

Projekt data-engineering + GenAI: „chat with data" na danych NYC Taxi.
Pełny design: `docs/DESIGN.md`. Plan bieżącej fazy: `docs/superpowers/plans/`.

## Status
- [x] Faza 0: setup
- [ ] Faza 1: batch ingestion (Parquet → GCS → BigQuery raw)
- [ ] Faza 2: hurtownia (dbt, star schema)
- [ ] Faza 3: GenAI (RAG + NL2SQL + guardraile)
- [ ] Faza 4: streaming (Pub/Sub)
- [ ] Faza 5: FastAPI + front
- [ ] Faza 6: ewaluacja + Airflow
- [ ] Faza 7: DevSecOps

## Uruchomienie (Faza 1)
1. Warunki wstępne GCP — patrz plan w `docs/superpowers/plans/`.
2. `python3 -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp .env.example .env` i uzupełnij `GCP_PROJECT_ID`, `GCS_BUCKET`.
5. `python -m ingestion.download`
6. `python -m ingestion.batch_load`

## Mapa na wymagania oferty
Patrz sekcja 10 w `docs/DESIGN.md`.
```

- [ ] **Step 5: Utwórz venv i zainstaluj zależności**

Run:
```bash
cd ~/dev/taxi-chat-data
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Expected: instalacja bez błędów, na końcu `Successfully installed ...`

- [ ] **Step 6: Commit**

```bash
cd ~/dev/taxi-chat-data
git add .gitignore .env.example requirements.txt README.md ingestion/__init__.py tests/__init__.py
git commit -m "chore: szkielet projektu (gitignore, env, deps, README)"
```

---

## Task 2: Config z env (`ingestion/config.py`)

**Files:**
- Create: `ingestion/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: zmienne env z `.env` (Task 1)
- Produces: funkcja `load_config() -> Config`, gdzie `Config` to dataclass z
  polami: `project_id: str`, `bucket: str`, `dataset_raw: str`, `location: str`,
  `data_dir: str`, `taxi_month: str`. Podnosi `ValueError` gdy brakuje
  wymaganego pola (`project_id`, `bucket`).

- [ ] **Step 1: Napisz failing test**

```python
# tests/test_config.py
import pytest
from ingestion.config import load_config, Config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj-x")
    monkeypatch.setenv("GCS_BUCKET", "proj-x-lake")
    monkeypatch.setenv("BQ_DATASET_RAW", "raw")
    monkeypatch.setenv("BQ_LOCATION", "US")
    monkeypatch.setenv("TAXI_DATA_DIR", "./data")
    monkeypatch.setenv("TAXI_MONTH", "2023-01")

    cfg = load_config()

    assert isinstance(cfg, Config)
    assert cfg.project_id == "proj-x"
    assert cfg.bucket == "proj-x-lake"
    assert cfg.dataset_raw == "raw"
    assert cfg.taxi_month == "2023-01"


def test_load_config_missing_required_raises(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.setenv("GCS_BUCKET", "proj-x-lake")
    with pytest.raises(ValueError, match="GCP_PROJECT_ID"):
        load_config()
```

- [ ] **Step 2: Uruchom test — ma FAIL**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.config'`

- [ ] **Step 3: Napisz minimalną implementację**

```python
# ingestion/config.py
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # wczytuje .env jeśli istnieje; env systemowy ma pierwszeństwo


@dataclass
class Config:
    project_id: str
    bucket: str
    dataset_raw: str
    location: str
    data_dir: str
    taxi_month: str


def load_config() -> Config:
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        raise ValueError("Brak wymaganej zmiennej GCP_PROJECT_ID (uzupełnij .env)")
    bucket = os.getenv("GCS_BUCKET")
    if not bucket:
        raise ValueError("Brak wymaganej zmiennej GCS_BUCKET (uzupełnij .env)")
    return Config(
        project_id=project_id,
        bucket=bucket,
        dataset_raw=os.getenv("BQ_DATASET_RAW", "raw"),
        location=os.getenv("BQ_LOCATION", "US"),
        data_dir=os.getenv("TAXI_DATA_DIR", "./data"),
        taxi_month=os.getenv("TAXI_MONTH", "2023-01"),
    )
```

- [ ] **Step 4: Uruchom test — ma PASS**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestion/config.py tests/test_config.py
git commit -m "feat: config z env (load_config, Config dataclass)"
```

---

## Task 3: Pobranie Parquet NYC Taxi (`ingestion/download.py`)

**Kontekst danych:** NYC TLC publikuje pliki Parquet pod stałym URL-em:
`https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_YYYY-MM.parquet`
(np. `yellow_tripdata_2023-01.parquet`, ~50 MB, ~3 mln wierszy — mały wycinek OK).

**Files:**
- Create: `ingestion/download.py`
- Test: `tests/test_download.py`

**Interfaces:**
- Consumes: `Config` z `load_config()` (Task 2)
- Produces: `build_taxi_url(month: str) -> str` oraz
  `download_taxi_parquet(cfg: Config) -> str` (zwraca lokalną ścieżkę pobranego
  pliku; jeśli plik już istnieje, nie pobiera ponownie).

- [ ] **Step 1: Napisz failing test**

```python
# tests/test_download.py
import os
import pytest
from ingestion.config import Config
from ingestion.download import build_taxi_url, download_taxi_parquet


def test_build_taxi_url():
    url = build_taxi_url("2023-01")
    assert url == (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/"
        "yellow_tripdata_2023-01.parquet"
    )


def test_download_skips_if_exists(tmp_path, monkeypatch):
    # plik już istnieje → download nie próbuje sieci, zwraca ścieżkę
    existing = tmp_path / "yellow_tripdata_2023-01.parquet"
    existing.write_bytes(b"fake")
    cfg = Config(
        project_id="p", bucket="b", dataset_raw="raw", location="US",
        data_dir=str(tmp_path), taxi_month="2023-01",
    )

    def _fail(*a, **k):
        raise AssertionError("nie powinno pobierać, plik istnieje")

    monkeypatch.setattr("ingestion.download.requests.get", _fail)

    path = download_taxi_parquet(cfg)
    assert path == str(existing)
    assert os.path.exists(path)
```

- [ ] **Step 2: Uruchom test — ma FAIL**

Run: `.venv/bin/python -m pytest tests/test_download.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.download'`

- [ ] **Step 3: Napisz implementację**

```python
# ingestion/download.py
import os

import requests

from ingestion.config import Config

BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


def build_taxi_url(month: str) -> str:
    return f"{BASE_URL}/yellow_tripdata_{month}.parquet"


def download_taxi_parquet(cfg: Config) -> str:
    os.makedirs(cfg.data_dir, exist_ok=True)
    filename = f"yellow_tripdata_{cfg.taxi_month}.parquet"
    dest = os.path.join(cfg.data_dir, filename)
    if os.path.exists(dest):
        print(f"[download] plik już istnieje, pomijam: {dest}")
        return dest
    url = build_taxi_url(cfg.taxi_month)
    print(f"[download] pobieram {url}")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"[download] zapisano {dest}")
    return dest


if __name__ == "__main__":
    from ingestion.config import load_config

    download_taxi_parquet(load_config())
```

- [ ] **Step 4: Uruchom test — ma PASS**

Run: `.venv/bin/python -m pytest tests/test_download.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Pobierz realny plik (dym-test manualny)**

Run (po uzupełnieniu `.env`):
```bash
cp .env.example .env   # jeśli jeszcze nie ma; uzupełnij GCP_PROJECT_ID, GCS_BUCKET
.venv/bin/python -m ingestion.download
```
Expected: pojawia się `data/yellow_tripdata_2023-01.parquet` (~50 MB).
Sprawdź: `ls -lh data/`

- [ ] **Step 6: Commit**

```bash
git add ingestion/download.py tests/test_download.py
git commit -m "feat: pobieranie Parquet NYC Taxi (idempotentne)"
```

---

## Task 4: Batch load Parquet → GCS → BigQuery raw (`ingestion/batch_load.py`)

**Files:**
- Create: `ingestion/batch_load.py`
- Test: `tests/test_batch_load.py`

**Interfaces:**
- Consumes: `Config` (Task 2), lokalny plik Parquet z `download_taxi_parquet` (Task 3)
- Produces:
  - `ensure_bucket(cfg: Config) -> None` — tworzy bucket GCS jeśli nie istnieje
  - `upload_to_gcs(cfg: Config, local_path: str) -> str` — zwraca `gs://...` URI
  - `ensure_dataset(cfg: Config) -> None` — tworzy dataset `raw` jeśli nie istnieje
  - `load_gcs_to_bq(cfg: Config, gcs_uri: str) -> int` — ładuje do `raw.trips`
    (autodetekcja schematu, WRITE_TRUNCATE), zwraca liczbę załadowanych wierszy
  - `run_batch(cfg: Config, local_path: str) -> int` — spina powyższe

**Uwaga o testach:** ten task woła realne GCP (GCS+BQ) — nie mockujemy klientów
chmury w unit-testach (byłoby to atrapowanie całej logiki). Zamiast tego:
- **unit-test** tylko czystej funkcji pomocniczej `blob_name_for(local_path)`,
- **integracyjny smoke-test** (`@pytest.mark.integration`) uruchamiany ręcznie po
  skonfigurowaniu GCP — nie w domyślnym `pytest`.

- [ ] **Step 1: Napisz failing test (czysta funkcja + marker integracyjny)**

```python
# tests/test_batch_load.py
import pytest
from ingestion.config import Config
from ingestion.batch_load import blob_name_for


def test_blob_name_for_strips_directory():
    assert blob_name_for("./data/yellow_tripdata_2023-01.parquet") == (
        "raw/yellow_tripdata_2023-01.parquet"
    )


@pytest.mark.integration
def test_run_batch_loads_rows():
    # RĘCZNY smoke-test: wymaga skonfigurowanego GCP + pobranego pliku.
    # Uruchom: pytest tests/test_batch_load.py -m integration -v
    from ingestion.config import load_config
    from ingestion.download import download_taxi_parquet
    from ingestion.batch_load import run_batch

    cfg = load_config()
    path = download_taxi_parquet(cfg)
    rows = run_batch(cfg, path)
    assert rows > 0
```

- [ ] **Step 2: Zarejestruj marker `integration` i uruchom test — ma FAIL**

Utwórz `pytest.ini`:
```ini
[pytest]
markers =
    integration: testy dotykające realnego GCP (uruchamiane ręcznie)
addopts = -m "not integration"
```

Run: `.venv/bin/python -m pytest tests/test_batch_load.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.batch_load'`
(test integracyjny pominięty przez `addopts`).

- [ ] **Step 3: Napisz implementację**

```python
# ingestion/batch_load.py
import os

from google.cloud import bigquery, storage

from ingestion.config import Config


def blob_name_for(local_path: str) -> str:
    """Ścieżka obiektu w buckecie: warstwa raw/ + nazwa pliku."""
    return f"raw/{os.path.basename(local_path)}"


def ensure_bucket(cfg: Config) -> None:
    client = storage.Client(project=cfg.project_id)
    if client.lookup_bucket(cfg.bucket) is None:
        client.create_bucket(cfg.bucket, location=cfg.location)
        print(f"[gcs] utworzono bucket {cfg.bucket}")
    else:
        print(f"[gcs] bucket {cfg.bucket} już istnieje")


def upload_to_gcs(cfg: Config, local_path: str) -> str:
    client = storage.Client(project=cfg.project_id)
    bucket = client.bucket(cfg.bucket)
    blob_name = blob_name_for(local_path)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    uri = f"gs://{cfg.bucket}/{blob_name}"
    print(f"[gcs] wgrano {uri}")
    return uri


def ensure_dataset(cfg: Config) -> None:
    client = bigquery.Client(project=cfg.project_id)
    dataset_id = f"{cfg.project_id}.{cfg.dataset_raw}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = cfg.location
    client.create_dataset(dataset, exists_ok=True)
    print(f"[bq] dataset {dataset_id} gotowy")


def load_gcs_to_bq(cfg: Config, gcs_uri: str) -> int:
    client = bigquery.Client(project=cfg.project_id)
    table_id = f"{cfg.project_id}.{cfg.dataset_raw}.trips"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )
    load_job = client.load_table_from_uri(gcs_uri, table_id, job_config=job_config)
    load_job.result()  # czeka na zakończenie
    table = client.get_table(table_id)
    print(f"[bq] załadowano {table.num_rows} wierszy do {table_id}")
    return table.num_rows


def run_batch(cfg: Config, local_path: str) -> int:
    ensure_bucket(cfg)
    gcs_uri = upload_to_gcs(cfg, local_path)
    ensure_dataset(cfg)
    return load_gcs_to_bq(cfg, gcs_uri)


if __name__ == "__main__":
    from ingestion.config import load_config
    from ingestion.download import download_taxi_parquet

    cfg = load_config()
    path = download_taxi_parquet(cfg)
    run_batch(cfg, path)
```

- [ ] **Step 4: Uruchom unit-test — ma PASS**

Run: `.venv/bin/python -m pytest tests/test_batch_load.py -v`
Expected: PASS (1 passed — `test_blob_name_for_strips_directory`;
test integracyjny pominięty).

- [ ] **Step 5: Uruchom integracyjny smoke-test (RĘCZNIE, po konfiguracji GCP)**

Warunek: wykonane P1–P3 (konto, gcloud, ADC) i uzupełniony `.env`.

Run:
```bash
.venv/bin/python -m pytest tests/test_batch_load.py -m integration -v
```
Expected: PASS — w BigQuery pojawia się tabela `raw.trips` z >0 wierszy.

Weryfikacja niezależna:
```bash
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS n FROM \`TWOJ_PROJECT_ID.raw.trips\`"
```
Expected: `n` ≈ 3 mln (dla 2023-01).

- [ ] **Step 6: Commit**

```bash
git add ingestion/batch_load.py tests/test_batch_load.py pytest.ini
git commit -m "feat: batch load Parquet -> GCS -> BigQuery raw.trips"
```

---

## Task 5: Uruchomienie całości end-to-end + weryfikacja Fazy 1

**Files:** brak nowych — to weryfikacja spójności.

**Interfaces:** korzysta z `ingestion.download` + `ingestion.batch_load`.

- [ ] **Step 1: Pełny przebieg jednym poleceniem**

Run:
```bash
.venv/bin/python -m ingestion.batch_load
```
Expected: kolejno logi `[download]`, `[gcs]`, `[bq]`, na końcu liczba wierszy.

- [ ] **Step 2: Sanity zapytanie w BQ (koszt bliski zeru — jedna kolumna)**

Run:
```bash
bq query --use_legacy_sql=false \
  "SELECT MIN(tpep_pickup_datetime) AS od, MAX(tpep_pickup_datetime) AS do,
          COUNT(*) AS n
   FROM \`TWOJ_PROJECT_ID.raw.trips\`"
```
Expected: zakres dat obejmuje wybrany miesiąc, `n` > 0.

- [ ] **Step 3: Zaktualizuj status w README**

W `README.md` zmień `- [ ] Faza 1` na `- [x] Faza 1`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: Faza 1 (batch ingestion) ukończona i zweryfikowana"
```

---

## Self-Review (wykonane przy pisaniu planu)

**Spec coverage (Faza 0 + 1 z DESIGN.md sekcje 8, 4, 7):**
- Setup repo/env/venv → Task 1 ✅
- GCP projekt + free tier + ADC → Warunki wstępne P1–P3 ✅
- Data Lake (GCS bucket, warstwa raw) → Task 4 `ensure_bucket`/`upload_to_gcs` ✅
- Batch: Parquet → GCS → BQ `raw.trips` → Task 3 + Task 4 ✅
- Load surowy bez transformacji (dbt w Fazie 2) → `autodetect`, WRITE_TRUNCATE ✅
- DevSecOps (sekrety poza repo) → `.gitignore` + ADC zamiast klucza w repo ✅
- Mały wycinek pod free tier → jeden miesiąc (`TAXI_MONTH`) ✅

**Poza zakresem tego planu (kolejne fazy, własne plany):** streaming/Pub/Sub
(Faza 4), dbt/star schema (Faza 2), Airflow (Faza 6 — Docker już sprawdzony
w środowisku), GenAI (Faza 3), walidacja schematu/dead-letter (dojdzie przy dbt
staging, Faza 2).

**Placeholder scan:** brak TODO/TBD, każdy krok ma pełny kod/komendę. ✅

**Type consistency:** `Config` (project_id, bucket, dataset_raw, location,
data_dir, taxi_month) spójny w Task 2→3→4. `load_config`, `download_taxi_parquet`,
`run_batch`, `blob_name_for` — nazwy zgodne między definicją a użyciem. ✅
