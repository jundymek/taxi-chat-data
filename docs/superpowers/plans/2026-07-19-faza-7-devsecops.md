# Faza 7 — DevSecOps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the roadmap by adding CI (lint, unit tests, dbt parse), secret scanning over the full git history, a single profile-based `docker-compose.yml` for the whole local stack, and a README that maps the project onto the job posting's requirements.

**Architecture:** Task 1 adds a root `pyproject.toml` (ruff config only) plus `requirements-dev.txt`, fixes the 34 lint findings that exist today, and lands `.github/workflows/ci.yml` with three parallel jobs. Task 2 adds a fourth job (gitleaks) and `.gitleaks.toml`. Task 3 merges `docker-compose.airflow.yml` into `docker-compose.yml` behind profiles and adds an `api` service. Task 4 rewrites `README.md` from the actual repo state.

**Tech Stack:** ruff, pytest 8, dbt-bigquery 1.8.x, GitHub Actions (`actions/setup-python@v5`, `actions/checkout@v4`, `gitleaks/gitleaks-action@v2`), Docker Compose profiles, `python:3.14-slim`.

**Spec:** `docs/superpowers/specs/2026-07-19-faza-7-devsecops-design.md`

## Global Constraints

- **No GCP credentials in CI.** No service-account keys, no Workload Identity Federation. `dbt test` stays local/Airflow-driven; CI only runs `dbt parse`.
- **No `ruff format` gate.** `ruff check` only. Running `ruff format` would reformat 33 of 44 files — an out-of-scope style diff. Do not run it, not even "just to see".
- **Ruff rule set is fixed:** `select = ["E", "F", "I", "UP", "B"]`, `line-length = 100`, `target-version = "py314"`. Do not add rules; do not switch to `ALL`.
- **Python 3.14** for all project code and CI jobs. The Airflow container is `apache/airflow:2.10.4-python3.11` and stays that way — do not "upgrade" it for consistency.
- **dbt-bigquery pin is `>=1.8,<2.0`** everywhere it appears (`requirements-dev.txt`, compose `_PIP_ADDITIONAL_REQUIREMENTS`, `dbt/Dockerfile`).
- **Ollama runs on the host**, never in a container. Services reach it at `http://host.docker.internal:11434`.
- **Docs and code in English.** Learning notes in Polish (this project's standing rule).
- **No AI-attribution footer** in commit messages.
- **Commit after every task.** Do not batch multiple tasks into one commit.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `pyproject.toml` | create (T1) | ruff configuration only — no build-system, no PEP 621 metadata |
| `requirements-dev.txt` | create (T1) | dev-only deps: ruff, pytest, dbt-bigquery |
| `requirements.txt` | modify (T1) | drop `pytest` (moves to dev) |
| `.github/workflows/ci.yml` | create (T1), modify (T2) | lint / test / dbt jobs, then the secrets job |
| `.gitleaks.toml` | create (T2) | extends default rules; allowlists `.env.example` |
| `docker-compose.yml` | modify (T3) | all four services behind profiles |
| `docker-compose.airflow.yml` | delete (T3) | merged into the above |
| `api/Dockerfile` | create (T3) | runtime image for the FastAPI service |
| `docs/features/faza-6-eval-airflow/faza-6-task-3/README.md` | modify (T3) | commands changed by the compose merge |
| `README.md` | rewrite (T4) | project front page + requirements map |
| various `.py` | modify (T1) | 34 lint fixes across `api/ genai/ ingestion/ tests/` |

Tasks 1 and 2 both touch `.github/workflows/ci.yml`, so they are sequential. Task 4 documents Task 3's commands, so it goes last.

---

## Task 1: ruff configuration, lint fixes, and CI

**Files:**
- Create: `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml`
- Modify: `requirements.txt`
- Modify (auto-fix): `api/main.py`, `api/schemas.py`, `ingestion/stream_consumer.py`, `tests/test_api_schemas.py`, `tests/test_batch_load.py`, `tests/test_config.py`, `tests/test_download.py`, `tests/test_indexer.py`, `tests/test_retriever.py`, `tests/test_stream_common.py`, `tests/test_stream_consumer.py`, `tests/test_guardrails.py`
- Modify (manual): `genai/eval.py`, `genai/guardrails.py`, `genai/nl2sql.py`, `tests/test_api_chat.py`, `tests/test_eval.py`, `tests/test_genai_types.py`, `tests/test_nl2sql.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `requirements-dev.txt` (Task 3's `api/Dockerfile` deliberately does *not* install it); `.github/workflows/ci.yml` with a top-level `jobs:` mapping that Task 2 appends a `secrets:` job to.

- [ ] **Step 1: Create the ruff configuration**

Create `pyproject.toml`:

```toml
# Ruff configuration only. The project installs dependencies via
# `pip install -r requirements.txt`, so there is deliberately no
# [build-system] or [project] table here.
[tool.ruff]
target-version = "py314"
line-length = 100
exclude = [".venv", "dbt/target", "dbt/dbt_packages", "frontend"]

[tool.ruff.lint]
# Deliberately narrow: pycodestyle errors, pyflakes, import sorting,
# pyupgrade, bugbear. Not ALL — this is a correctness gate, not a
# style migration.
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 2: Create the dev requirements file**

Create `requirements-dev.txt`:

```
# Dev/CI-only dependencies. Runtime deps live in requirements.txt.
ruff>=0.6
pytest>=8.0
# Pinned to match the Airflow service and dbt/Dockerfile.
dbt-bigquery>=1.8,<2.0
```

- [ ] **Step 3: Remove pytest from the runtime requirements**

In `requirements.txt`, delete the line `pytest>=8.0`. Leave every other line untouched.

- [ ] **Step 4: Install ruff and confirm the baseline**

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check .
```

Expected: `Found 34 errors.` with `[*] 18 fixable with the --fix option`.

If the count differs, the tree has drifted since planning — stop and report the actual output rather than proceeding.

- [ ] **Step 5: Apply the automatic fixes**

```bash
.venv/bin/ruff check --fix .
```

This resolves 18 findings: `I001` (unsorted imports) in 9 files, `UP017` (`datetime.timezone.utc` → `datetime.UTC`) in 5 places, `F401` (unused `pytest` in `tests/test_guardrails.py`, unused `json` and `pytest` in `tests/test_stream_consumer.py`), and one `UP012` (unnecessary `.encode("utf-8")`).

Expected after the run: `Found 16 errors.` — all now requiring manual edits.

- [ ] **Step 6: Verify the auto-fixes broke nothing**

```bash
.venv/bin/pytest
```

Expected: the whole suite passes (integration tests are excluded by `pytest.ini`'s `addopts = -m "not integration"`). `UP017` rewrote `datetime` usage, so a green suite here is the real check.

- [ ] **Step 7: Fix `B905` — zip without `strict=`**

`genai/eval.py:90`. Add `strict=True` to the `zip(...)` call: the two sequences are expected to be the same length, and a silent truncation would corrupt an eval comparison. Example shape:

```python
# before
for a, b in zip(left, right):
# after
for a, b in zip(left, right, strict=True):
```

- [ ] **Step 8: Fix `UP028` — yield over for loop**

`tests/test_api_chat.py:21`. Replace the loop with `yield from`:

```python
# before
def fake_stream():
    for frame in frames:
        yield frame
# after
def fake_stream():
    yield from frames
```

Match the surrounding names as they actually appear in the file.

- [ ] **Step 9: Fix `E741` — ambiguous variable name**

`tests/test_eval.py:164`. Rename the variable `l` to something descriptive of what it holds (e.g. `line` or `left`). Rename every reference within its scope.

- [ ] **Step 10: Fix the 13 `E501` long lines**

List them:

```bash
.venv/bin/ruff check --select E501 --output-format concise .
```

Locations: `genai/eval.py:167`, `genai/guardrails.py:25`, `genai/guardrails.py:79`, `genai/nl2sql.py:48`, `tests/test_eval.py:100`, `tests/test_eval.py:108`, `tests/test_genai_types.py:12`, `tests/test_guardrails.py:128`, `tests/test_nl2sql.py:6`, `tests/test_pipeline.py:86`, `tests/test_pipeline.py:137`, `tests/test_pipeline.py:148`, `tests/test_retriever.py:25`.

Wrap each by hand — break long strings across implicitly-concatenated literals, or split call arguments across lines. Do not raise `line-length`, and do not add `# noqa`. Preserve the exact text of any SQL or prompt string: only its line breaks may change.

- [ ] **Step 11: Verify lint is clean and tests still pass**

```bash
.venv/bin/ruff check .
.venv/bin/pytest
```

Expected: `All checks passed!` and a green test suite.

- [ ] **Step 12: Commit the lint work**

```bash
git add pyproject.toml requirements-dev.txt requirements.txt api genai ingestion tests
git commit -m "chore: add ruff config and fix existing lint findings"
```

- [ ] **Step 13: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
      - run: pip install ruff
      # `ruff format` is deliberately not a gate — see the Faza 7 design doc.
      - run: ruff check .

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
      - run: pip install -r requirements.txt -r requirements-dev.txt
      # pytest.ini sets `-m "not integration"`, so GCP-touching tests are
      # excluded. No GOOGLE_* env vars here on purpose: if an unmarked test
      # reaches for BigQuery, this job should fail and the marker gets added.
      - run: pytest

  dbt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
          cache: pip
      - run: pip install "dbt-bigquery>=1.8,<2.0"
      # `dbt parse` validates model SQL, ref()/source() wiring and the schema
      # YAML without opening a BigQuery connection, so no credentials needed.
      - run: dbt deps
        working-directory: dbt
      - run: dbt parse
        working-directory: dbt
```

- [ ] **Step 14: Verify `dbt parse` really works without credentials**

```bash
cd dbt && DBT_PROFILES_DIR=. dbt deps && DBT_PROFILES_DIR=. dbt parse; cd ..
```

Expected: parse succeeds.

If it instead fails asking for credentials, apply the spec's documented fallback: add `--no-partial-parse`, and if that is still insufficient, create `dbt/profiles.ci.yml` holding a fixture profile (same structure as `dbt/profiles.yml`, `method: oauth`, `project: taxi-chat-data-ci`) and point the CI steps at it with `--profiles-dir . --target ci`. Record which variant was needed in the commit message.

- [ ] **Step 15: Commit the workflow**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run ruff, pytest and dbt parse on push and PR"
```

- [ ] **Step 16: Push and confirm CI is green**

```bash
git push -u origin feat/faza-7-devsecops
gh run watch
```

Expected: all three jobs pass. Do not proceed to Task 2 until they do — Task 2 edits the same file.

---

## Task 2: gitleaks secret scanning

**Files:**
- Create: `.gitleaks.toml`
- Modify: `.github/workflows/ci.yml` (append a fourth job)

**Interfaces:**
- Consumes: the `jobs:` mapping created in Task 1.
- Produces: nothing consumed by later tasks. Task 4 describes this job in the README's DevSecOps section.

- [ ] **Step 1: Create the gitleaks configuration**

Create `.gitleaks.toml`:

```toml
# Extends the upstream default rule set rather than replacing it.
[extend]
useDefault = true

# .env.example ships placeholder values (GCP_PROJECT_ID=your-project-id and
# similar) that can trip generic-credential heuristics. Scope the exception to
# that one path — never suppress a rule globally.
[[allowlist.paths]]
path = '''^\.env\.example$'''
```

- [ ] **Step 2: Append the secrets job to the workflow**

Add to the end of `.github/workflows/ci.yml`, at the same indentation as the `lint`, `test` and `dbt` jobs:

```yaml
  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Full history: a secret that was committed and later reverted is
          # still leaked, and a shallow clone would not see it.
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 3: Verify the config is valid and the current tree is clean**

```bash
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest detect \
  --source=/repo --config=/repo/.gitleaks.toml --verbose
```

Expected: `no leaks found`.

If it reports leaks in the real history, stop and report them — that is a genuine finding to handle deliberately, not something to allowlist away.

- [ ] **Step 4: Prove the scanner actually fails on a planted secret**

A gate that has never failed is not known to work. On a throwaway branch:

```bash
git checkout -b tmp/gitleaks-selftest
printf 'aws_secret_access_key = "AKIAIOSFODNN7EXAMPLE"\n' > /tmp/leak_probe.txt
git add -f /tmp/leak_probe.txt 2>/dev/null || cp /tmp/leak_probe.txt ./leak_probe.txt && git add leak_probe.txt
git commit -m "test: planted secret (never merged)"
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest detect \
  --source=/repo --config=/repo/.gitleaks.toml --verbose
```

Expected: gitleaks reports a finding and exits non-zero.

- [ ] **Step 5: Destroy the self-test branch**

```bash
git checkout feat/faza-7-devsecops
git branch -D tmp/gitleaks-selftest
rm -f leak_probe.txt /tmp/leak_probe.txt
git status
```

Expected: clean tree, no `leak_probe.txt` anywhere, `tmp/gitleaks-selftest` gone. **Never push that branch.**

- [ ] **Step 6: Commit**

```bash
git add .gitleaks.toml .github/workflows/ci.yml
git commit -m "ci: scan full git history for secrets with gitleaks"
```

- [ ] **Step 7: Push and confirm all four jobs pass**

```bash
git push && gh run watch
```

Expected: `lint`, `test`, `dbt`, `secrets` all green.

---

## Task 3: unified docker-compose with profiles

**Files:**
- Create: `api/Dockerfile`
- Modify: `docker-compose.yml`
- Delete: `docker-compose.airflow.yml`
- Modify: `docs/features/faza-6-eval-airflow/faza-6-task-3/README.md`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: the compose profile commands (`--profile dbt|airflow|api`) that Task 4's README quickstart documents verbatim.

- [ ] **Step 1: Create the API Dockerfile**

Create `api/Dockerfile`:

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Runtime deps only — requirements-dev.txt (ruff, pytest) stays out of the image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY genai ./genai

# No --reload: this image exists so the project starts with one command.
# The day-to-day dev loop stays native uvicorn on the host.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note the build context must be the repo root (set in the compose file below), because the image needs both `api/` and `genai/`.

- [ ] **Step 2: Write the unified compose file**

Replace the entire contents of `docker-compose.yml`:

```yaml
# Local stack for taxi-chat-data. Every service sits behind a profile, so a bare
# `docker compose up` starts nothing — you pick what you need:
#
#   docker compose --profile api up                     # FastAPI on :8000
#   docker compose --profile airflow up -d              # Airflow UI on :8080
#   docker compose --profile dbt run --rm dbt build     # one-off dbt command
#   docker compose --profile airflow --profile api up   # both
#
# Ollama deliberately runs on the HOST, not here: a container on macOS gets no
# GPU access and would re-download ~10 GB of models you already have. Services
# reach it through host.docker.internal.
services:
  dbt:
    profiles: [dbt]
    build:
      context: ./dbt
      dockerfile: Dockerfile
    working_dir: /usr/app/dbt
    volumes:
      # Project files (models, seeds, profiles) — live-editable from host.
      - ./dbt:/usr/app/dbt
      # ADC credentials, read-only, so the container authenticates as you.
      - ~/.config/gcloud:/root/.config/gcloud:ro
    environment:
      - GOOGLE_CLOUD_PROJECT=taxi-chat-data

  postgres:
    profiles: [airflow]
    image: postgres:16
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - airflow-db:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      interval: 5s
      retries: 5

  airflow:
    profiles: [airflow]
    image: apache/airflow:2.10.4-python3.11
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      AIRFLOW__CORE__EXECUTOR: LocalExecutor
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@postgres/airflow
      AIRFLOW__CORE__LOAD_EXAMPLES: "false"
      # ADC for dbt-bigquery (mounted read-only below).
      GOOGLE_APPLICATION_CREDENTIALS: /opt/airflow/gcloud/application_default_credentials.json
      GOOGLE_CLOUD_PROJECT: taxi-chat-data
      OLLAMA_HOST: http://host.docker.internal:11434
      # Match the project's own dbt Dockerfile pin. (The DAG copies the mounted
      # dbt project into a writable temp dir before running, so dbt deps/target/
      # logs never need to write to the host-owned bind mount — portable to Linux.)
      _PIP_ADDITIONAL_REQUIREMENTS: "dbt-bigquery>=1.8,<2.0"
    volumes:
      - ./dags:/opt/airflow/dags
      - ./dbt:/opt/airflow/dbt
      # ${HOME} (not ~): Compose always expands ${HOME} in a bind source, but a
      # leading ~ is only expanded by some Compose versions — using ${HOME}
      # avoids a host-dependent "credentials not found" failure.
      - ${HOME}/.config/gcloud/application_default_credentials.json:/opt/airflow/gcloud/application_default_credentials.json:ro
    ports:
      - "8080:8080"
    extra_hosts:
      # No-op on macOS, required on Linux — kept for portability.
      - "host.docker.internal:host-gateway"
    command: standalone

  api:
    profiles: [api]
    build:
      # Repo root: the image needs both api/ and genai/.
      context: .
      dockerfile: api/Dockerfile
    ports:
      - "8000:8000"
    environment:
      GOOGLE_APPLICATION_CREDENTIALS: /root/.config/gcloud/application_default_credentials.json
      GOOGLE_CLOUD_PROJECT: taxi-chat-data
      OLLAMA_HOST: http://host.docker.internal:11434
    env_file:
      - .env
    volumes:
      # ADC read-only — the API queries BigQuery.
      - ~/.config/gcloud:/root/.config/gcloud:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"

volumes:
  airflow-db:
```

- [ ] **Step 3: Delete the superseded Airflow compose file**

```bash
git rm docker-compose.airflow.yml
```

- [ ] **Step 4: Validate the merged file parses**

```bash
docker compose --profile airflow --profile api --profile dbt config >/dev/null && echo OK
```

Expected: `OK`. A YAML or reference error surfaces here.

- [ ] **Step 5: Verify the API profile serves traffic**

```bash
docker compose --profile api up -d --build
sleep 15
curl -sf http://localhost:8000/health && echo "" && curl -sfI http://localhost:8000/docs | head -1
docker compose --profile api down
```

Expected: `/health` returns JSON and `/docs` returns `HTTP/1.1 200 OK`.

If `genai.config` requires an env var missing from `.env`, add it to `.env.example` too (placeholder value only — gitleaks allowlists that file, so never put a real value there).

- [ ] **Step 6: Verify the Airflow profile still runs the Faza 6 DAG**

This is the regression that matters: the merge must not break Task 3 of Faza 6.

```bash
docker compose --profile airflow up -d
sleep 45
docker compose exec airflow airflow dags list | grep dbt_transform
docker compose exec airflow airflow dags trigger dbt_transform
```

Expected: the DAG is listed and triggers without error. Check the run reaches success in the UI at http://localhost:8080 (the standalone password is in `docker compose logs airflow | grep -i password`).

```bash
docker compose --profile airflow down
```

- [ ] **Step 7: Update the Faza 6 Task 3 doc**

In `docs/features/faza-6-eval-airflow/faza-6-task-3/README.md`, replace every `docker compose -f docker-compose.airflow.yml <cmd>` with `docker compose --profile airflow <cmd>`. Read the file first and update the surrounding prose where it refers to a separate Airflow compose file — leaving stale instructions behind is the failure mode this step exists to prevent.

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml api/Dockerfile docs/features/faza-6-eval-airflow/faza-6-task-3/README.md
git add -u
git commit -m "build: unify docker-compose behind dbt/airflow/api profiles"
```

- [ ] **Step 9: Push and confirm CI is still green**

```bash
git push && gh run watch
```

Expected: four green jobs.

---

## Task 4: README as the project front page

**Files:**
- Modify: `README.md` (full rewrite, ~200–250 lines)

**Interfaces:**
- Consumes: the compose profile commands from Task 3, the CI job names from Tasks 1–2.
- Produces: nothing.

- [ ] **Step 1: Gather the real numbers and status — do not write from memory**

```bash
cat docs/eval/latest.md
ls docs/features/
git log --oneline | head -20
```

Every figure and phase status in the README must come from this output. As of planning, `docs/eval/latest.md` reports 18 questions, gemma4 67% accuracy / 94% executed / 1.44 avg attempts / 1 refusal, llama3.1:8b 61% / 78% / 1.50 / 4 — re-read it, because Faza 6 output may have been regenerated since.

- [ ] **Step 2: Write the header, architecture diagram, and quickstart**

Replace the top of `README.md` with:

````markdown
# taxi-chat-data

An end-to-end data-engineering + GenAI project on NYC Taxi data: batch and
streaming ingestion into BigQuery, a dbt star schema on top, and a natural-language
chat interface that answers questions by generating SQL against the warehouse.

Design document: [docs/DESIGN.md](docs/DESIGN.md) · Phase plans: [docs/superpowers/plans/](docs/superpowers/plans/)

## Architecture

```mermaid
flowchart LR
  P[Parquet<br/>NYC TLC] --> G[GCS raw]
  G --> BQR[(BigQuery<br/>raw)]
  PS[Pub/Sub<br/>trips-stream] --> BQS[(BigQuery<br/>stream.trips)]
  BQR --> DBT[dbt<br/>staging → marts]
  BQS --> DBT
  DBT --> DW[(Star schema<br/>partitioned + clustered)]
  DW --> GEN[genai<br/>RAG + NL2SQL + guardrails]
  OLL[Ollama<br/>host] --> GEN
  GEN --> API[FastAPI<br/>SSE /chat]
  API --> FE[Frontend]
  AF[Airflow] -.orchestrates.-> DBT
```

## Quickstart

**Prerequisites**

- Python 3.14 and Docker
- [Ollama](https://ollama.com) on the host with `gemma4`, `llama3.1:8b`, `nomic-embed-text`
- `gcloud auth application-default login` (the project uses ADC — never key files)

**Setup**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in GCP_PROJECT_ID and GCS_BUCKET
```

**Run**

```bash
docker compose --profile api up          # API + docs on http://localhost:8000/docs
docker compose --profile airflow up -d   # Airflow UI on http://localhost:8080
docker compose --profile dbt run --rm dbt build
```

Ollama stays on the host on purpose: a container on macOS gets no GPU access and
would re-download ~10 GB of models. Containers reach it via `host.docker.internal`.

For the frontend dev server, see [frontend/](frontend/) — it runs on `:3002`.
````

- [ ] **Step 3: Write the requirements map**

This section is the reason the task exists — every row links to real files, not abstract "blocks". Verify each path exists before writing it.

````markdown
## What this demonstrates

| Requirement | Where in the project |
|---|---|
| Batch + streaming pipeline | [ingestion/batch_load.py](ingestion/batch_load.py), [ingestion/stream_producer.py](ingestion/stream_producer.py), [ingestion/stream_consumer.py](ingestion/stream_consumer.py) |
| Data lake + warehouse | GCS raw layer + [dbt/models/](dbt/models/) star schema |
| Logical/physical modelling | [dbt/models/marts/](dbt/models/marts/) — dim/fct with partitioning and clustering |
| SQL optimisation in BigQuery | [analysis/measure_partitioning.py](analysis/measure_partitioning.py) — partition/cluster scan measurements |
| LLM / GenAI, chat with data | [genai/](genai/) + [api/main.py](api/main.py) |
| NL2SQL + risk mitigation | [genai/nl2sql.py](genai/nl2sql.py), [genai/guardrails.py](genai/guardrails.py) |
| RAG + vector store | [genai/retriever.py](genai/retriever.py), [genai/indexer.py](genai/indexer.py) (Chroma) |
| GenAI quality evaluation | [genai/eval.py](genai/eval.py), [docs/eval/latest.md](docs/eval/latest.md) |
| Orchestration | [dags/dbt_transform_dag.py](dags/dbt_transform_dag.py) (Airflow) |
| DevSecOps | ADC, [.gitleaks.toml](.gitleaks.toml), [.github/workflows/ci.yml](.github/workflows/ci.yml) |
| Python (advanced) | Whole codebase, [tests/](tests/) |
````

Paths verified at planning time: `analysis/measure_partitioning.py`, `dbt/models/marts/`, `dbt/models/staging/`, and `frontend/` all exist. Re-check with `ls` if the tree has drifted.

- [ ] **Step 4: Write the evaluation, DevSecOps, structure, phases and limitations sections**

````markdown
## Model evaluation

18 natural-language questions with reference SQL, scored on order-insensitive
result-set equality. Numbers from [docs/eval/latest.md](docs/eval/latest.md):

| Model | Accuracy | Executed | Avg attempts | Refusals |
|---|---|---|---|---|
| gemma4:latest | 67% | 94% | 1.44 | 1 |
| llama3.1:8b | 61% | 78% | 1.50 | 4 |

Regenerate with `python -m genai.eval`; the API also serves the latest report at
`GET /eval`.

## DevSecOps

- **Credentials:** Application Default Credentials only. No service-account keys
  exist in the project, and [.gitignore](.gitignore) blocks `*-key.json`,
  `*-sa.json`, `credentials.json` and `.env` so one cannot be added by accident.
- **Secret scanning:** gitleaks runs over the *full* git history on every push
  and PR — a secret that was committed and reverted is still a leak.
- **CI:** ruff (lint), pytest (unit), and `dbt parse` (model/YAML validation).
  `dbt parse` needs no BigQuery connection, so CI holds zero cloud credentials.
- **Cost control:** [genai/guardrails.py](genai/guardrails.py) validates generated
  SQL and runs a BigQuery dry-run to reject queries that would scan too much data.

## Repository layout

| Path | Contents |
|---|---|
| [ingestion/](ingestion/) | Batch loader, Pub/Sub producer and consumer |
| [dbt/](dbt/) | Staging models, star schema, tests |
| [genai/](genai/) | LLM client, RAG retriever, NL2SQL, guardrails, evaluation |
| [api/](api/) | FastAPI app, SSE streaming contract |
| [frontend/](frontend/) | Chat UI |
| [dags/](dags/) | Airflow DAGs |
| [tests/](tests/) | pytest suite |
| [docs/](docs/) | Design, specs, plans, per-phase feature docs |

## Build phases

- [x] Faza 0 — setup: repo, GCP project, `.env`
- [x] Faza 1 — batch ingestion: Parquet → GCS → BigQuery raw
- [x] Faza 2 — warehouse: dbt staging → star schema, partitioning and clustering
- [x] Faza 3 — GenAI: RAG + NL2SQL + guardrails
- [x] Faza 4 — streaming: Pub/Sub producer and consumer
- [x] Faza 5 — FastAPI + frontend
- [x] Faza 6 — evaluation, stream merge, Airflow
- [x] Faza 7 — DevSecOps: CI, secret scanning, unified compose

Per-phase detail lives in [docs/features/](docs/features/).

## Deliberate limitations

- **One month of data.** A small slice keeps the project inside the BigQuery free
  tier. Nothing in the design prevents scaling it up.
- **Neo4j / graph modelling deferred.** Listed as nice-to-have; it would not have
  changed the pipeline's shape.
- **Ollama on the host, not in Compose.** GPU access and a 10 GB model re-download.
- **`dbt test` runs locally and in Airflow, not in CI.** CI holds no GCP
  credentials by design, and `dbt test` requires a live warehouse.
````

Tick the Faza 7 box only once Tasks 1–3 are merged; if this task runs before that, leave it unchecked and check it in the final commit.

- [ ] **Step 5: Verify every relative link resolves**

```bash
grep -o ']([^)h][^)]*)' README.md | tr -d '](' | tr -d ')' | while read -r p; do
  [ -e "$p" ] || echo "BROKEN: $p"
done
```

Expected: no output.

- [ ] **Step 6: Confirm the mermaid block renders**

Push and open the file on GitHub — a syntax error shows as a raw code block instead of a diagram. Fix and amend if it does not render.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README as project front page with requirements map"
git push
```

- [ ] **Step 8: Final verification**

```bash
gh run watch
.venv/bin/ruff check . && .venv/bin/pytest
docker compose --profile airflow --profile api --profile dbt config >/dev/null && echo "compose OK"
```

Expected: four green CI jobs, clean lint, green tests, valid compose. Report the actual output — do not claim completion without it.

---

## Self-Review

**Spec coverage:** Task 7-1 → ruff config, `requirements-dev.txt`, three CI jobs, all 34 lint findings enumerated with exact locations. Task 7-2 → gitleaks job with `fetch-depth: 0`, `.gitleaks.toml` allowlisting only `.env.example`, plus the spec's planted-secret test and its cleanup. Task 7-3 → four services behind profiles, `api/Dockerfile`, Ollama on host with `extra_hosts`, deletion of `docker-compose.airflow.yml`, Faza 6 doc update, and the DAG regression check. Task 7-4 → all nine README sections from the spec. The spec's testing section maps to T1 S11/S16, T2 S3–S5, T3 S4–S6, T4 S5–S6.

**Deviation from spec, applied:** the spec's `ruff format --check` gate was removed after measuring that it would reformat 33 of 44 files. The spec was updated to match before this plan was written, so the two agree.

**Placeholder scan:** no TBD/TODO. Every lint fix names a file and line; every code step shows the code. The one branch point (`dbt parse` needing credentials) has its fallback written out rather than deferred.

**Consistency:** `dbt-bigquery>=1.8,<2.0` identical in `requirements-dev.txt`, the CI dbt job, and the Airflow service. Profile names `dbt`/`airflow`/`api` identical between Task 3's compose file and Task 4's README. Job names `lint`/`test`/`dbt`/`secrets` consistent between Tasks 1, 2 and 4. Python 3.14 everywhere except the intentionally pinned Airflow 3.11 image.
