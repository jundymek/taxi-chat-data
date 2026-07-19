# Faza 7 — DevSecOps: CI/CD, secret scanning, unified compose, README

**Date:** 2026-07-19
**Status:** approved (design), pending implementation plan

## Goal

Close the roadmap (`docs/DESIGN.md` §8, Faza 7): continuous integration, secret
scanning, one `docker-compose.yml` that starts the whole local stack, and a
README that a reviewer can read in five minutes to see how the project maps onto
the job posting's requirements.

## Non-goals

- No BigQuery access from CI. No service-account keys, no Workload Identity
  Federation. `dbt test` stays local / Airflow-driven (it already runs in the
  Faza 6 DAG).
- No Ollama container. Models stay on the host.
- No frontend container.
- No migration of `requirements.txt` to PEP 621. `pyproject.toml` is added for
  ruff configuration only.
- No repo-wide refactor. Ruff runs a conservative rule set so Task 7-1 stays a
  tooling task, not a rewrite.

## Tasks

Four independently mergeable tasks. 7-1 and 7-2 both edit `.github/workflows/ci.yml`,
so they land in order. 7-4 documents 7-3's commands, so it lands last.

| Task | Scope | Files |
|---|---|---|
| 7-1 | Ruff config + CI (lint, test, dbt parse) | `pyproject.toml`, `requirements-dev.txt`, `.github/workflows/ci.yml`, fixes across `api/ genai/ ingestion/ dags/ tests/` |
| 7-2 | Gitleaks job + allowlist | `.github/workflows/ci.yml`, `.gitleaks.toml` |
| 7-3 | Unified compose with profiles | `docker-compose.yml`, `api/Dockerfile`, delete `docker-compose.airflow.yml`, update Faza 6 Task 3 doc |
| 7-4 | README as the project's front page | `README.md` |

## Task 7-1: lint + CI

### Ruff configuration

New `pyproject.toml` at the repo root, ruff section only:

```toml
[tool.ruff]
target-version = "py314"
line-length = 100
exclude = [".venv", "dbt/target", "dbt/dbt_packages", "frontend"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Rule set chosen deliberately: pycodestyle errors, pyflakes, import sorting,
pyupgrade, and bugbear. Not `ALL` — the point is a clean gate on existing code,
not a style migration.

`dags/` is written for Airflow's Python 3.11 interpreter, not the project's 3.14.
Ruff's `target-version = "py314"` only affects `UP` suggestions; if any `UP` fix
in `dags/` would emit syntax the 3.11 image cannot parse, that file gets a
`per-file-ignores` entry rather than the fix. This is checked during
implementation, not assumed.

### requirements-dev.txt

New file: `ruff`, `dbt-bigquery>=1.8,<2.0` (matching the pin already used by the
Airflow service), and `pytest>=8.0` moved out of `requirements.txt`. Runtime
requirements should not carry the test runner.

### Workflow

`.github/workflows/ci.yml`, triggered on `push` to `master` and on
`pull_request`. Three parallel jobs so each failure is independently visible:

**`lint`** — `actions/setup-python@v5` (3.14, `cache: pip`) → `pip install ruff`
→ `ruff check .` → `ruff format --check .`.

**`test`** — setup-python 3.14 → `pip install -r requirements.txt -r
requirements-dev.txt` → `pytest`. The existing `pytest.ini` sets
`addopts = -m "not integration"`, so GCP-touching tests exclude themselves. No
`GOOGLE_*` env vars are provided: if an unmarked test reaches for BigQuery, CI
surfaces it and the missing `integration` marker gets added.

**`dbt`** — setup-python 3.14 → `pip install dbt-bigquery` → `dbt deps` →
`dbt parse`, run in `dbt/`. The repo's existing `dbt/profiles.yml` uses
`method: oauth`; `dbt parse` validates model SQL, `ref()`/`source()` resolution
and the YAML schema files without opening a BigQuery connection, so no
credentials are needed and no CI-specific profile is added. If `dbt parse` turns
out to require credentials in practice, the fallback is `dbt parse
--no-partial-parse` with `DBT_PROFILES_DIR` pointed at a fixture profile — the
implementation verifies which is needed rather than guessing.

## Task 7-2: secret scanning

Fourth job, `secrets`, in the same workflow: `actions/checkout@v4` with
`fetch-depth: 0`, then `gitleaks/gitleaks-action@v2`. Full history, not just the
diff — a secret committed earlier and reverted is still leaked.

`.gitleaks.toml` extends the default rule set and allowlists `.env.example`,
whose placeholder values (`GOOGLE_CLOUD_PROJECT=your-project` and similar) would
otherwise trip generic-credential heuristics. The allowlist is scoped to that
one path; no blanket rule suppressions.

This closes the loop with the existing `.gitignore`, which already blocks
`*-key.json`, `*-sa.json`, `credentials.json` and `.env`. The project
authenticates through ADC and has no key files by design; gitleaks enforces that
it stays that way.

## Task 7-3: unified docker-compose

One `docker-compose.yml`, four services, each behind a profile so a bare
`docker compose up` starts nothing and the choice is explicit:

| Service | Profile | Notes |
|---|---|---|
| `dbt` | `dbt` | unchanged: builds `./dbt`, ADC mounted read-only |
| `postgres` | `airflow` | Airflow metadata DB, healthcheck |
| `airflow` | `airflow` | LocalExecutor, waits for postgres healthy |
| `api` | `api` | new: builds `./api`, publishes 8000 |

Usage: `docker compose --profile api up`, `--profile airflow up`, or both
profiles together.

**Ollama stays on the host.** Every service gets
`OLLAMA_HOST=http://host.docker.internal:11434` and
`extra_hosts: ["host.docker.internal:host-gateway"]` — the latter is a no-op on
macOS but required on Linux, so it is present for portability. Rationale: a
containerised Ollama on macOS has no GPU access and would re-download ~10 GB of
models that already exist on the host. This trade-off is documented in the
README, not only in a YAML comment.

**`api/Dockerfile`** (new): `python:3.14-slim`, `pip install -r
requirements.txt`, entrypoint `uvicorn api.main:app --host 0.0.0.0 --port 8000`.
No `--reload` — the container exists so a reviewer can start the project with
one command; the day-to-day dev loop stays native uvicorn on the host. ADC is
mounted read-only, as the API queries BigQuery.

**Migration:** `docker-compose.airflow.yml` is merged into the main file under
the `airflow` profile and deleted. That changes the commands documented in
`docs/features/faza-6-eval-airflow/faza-6-task-3/README.md`, which is updated in
the same task so no dead instructions are left behind.

## Task 7-4: README

Rewritten as the project's front page, in English (project rule: code and docs in
English, learning notes in Polish). Target ~200–250 lines.

1. **Title + one sentence** — end-to-end NYC Taxi pipeline: batch and streaming
   ingestion → BigQuery → dbt star schema → NL2SQL chat over the warehouse.
2. **Architecture diagram** — a mermaid `flowchart LR` (GitHub renders it
   natively): Parquet→GCS→BQ raw and Pub/Sub→`stream.trips` feeding dbt
   staging→marts, then `genai` (RAG + NL2SQL + guardrails), FastAPI, frontend,
   with Airflow orchestrating dbt off to the side.
3. **Quickstart** — prerequisites (Python 3.14, Docker, Ollama with `gemma4`,
   `llama3.1:8b`, `nomic-embed-text`, gcloud ADC), `.env` from `.env.example`,
   the compose profile commands, and what to open (`:8000/docs`, `:8080`
   Airflow, `:3002` frontend).
4. **Requirements map** — the table from `DESIGN.md` §10, with every row linking
   to concrete files rather than to abstract "blocks". This section is the
   reason the task exists.
5. **Evaluation results** — the gemma4 vs llama3.1 summary, read from
   `docs/eval/latest.md` at implementation time (currently 18 questions;
   gemma4 67% vs llama3.1 61% accuracy), linking to the full report and the
   `GET /eval` endpoint.
6. **DevSecOps** — ADC instead of key files, `.gitignore` blocking key patterns,
   gitleaks over full history, guardrails with BigQuery dry-run as cost
   protection, and the CI gates from 7-1.
7. **Directory structure** — linked tree, one line per directory.
8. **Phases 0–7** — checklist of what was built, linking to
   `docs/features/faza-N-*`, showing the incremental path.
9. **Deliberate limitations** — small data slice, Neo4j deferred, Ollama on the
   host, `dbt test` outside CI. Naming trade-offs explicitly is stronger than
   pretending they don't exist.

Sections 5 and 8 must be written from the actual repository state — eval numbers
read from `docs/eval/latest.md`, phase status verified against `docs/features/`
and git history. No invented figures.

## Testing

- 7-1: CI is its own test — the workflow must pass on the branch before merge.
  `ruff check .` and `pytest` run locally first.
- 7-2: verified by a deliberate scratch commit containing a fake AWS-shaped key
  on a throwaway branch, confirming gitleaks fails the job, then discarding that
  branch. The scratch commit is never pushed to `master`.
- 7-3: `docker compose --profile api up` serves `:8000/docs`;
  `--profile airflow up` reaches the Airflow UI on `:8080` and the
  `dbt_transform` DAG still triggers successfully. `docker compose config`
  validates the merged file.
- 7-4: links checked (no 404s on relative paths), mermaid block renders on the
  GitHub PR preview.

## Risks

- **Ruff finds more than expected in existing code.** Mitigated by the narrow
  rule set. If a single file needs disproportionate churn, it gets a
  `per-file-ignores` entry and a follow-up note rather than blocking the task.
- **`dbt parse` may still want credentials.** Fallback documented in 7-1.
- **Merging the Airflow compose file could break the Faza 6 DAG workflow.**
  Mitigated by the explicit re-test in 7-3 and by updating the Faza 6 task doc
  in the same commit.
