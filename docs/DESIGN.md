# Projekt: „Chat with Data" na danych NYC Taxi — spec / design

> **Jak używać tego pliku:** to samodzielny spec. Utwórz świeży, pusty katalog
> (np. `taxi-chat-data/`), skopiuj do niego ten plik jako `docs/DESIGN.md`,
> otwórz w tym katalogu Claude Code i powiedz: *„Kontynuuj wg docs/DESIGN.md —
> zacznij od Fazy 0 (setup)."* Nowa sesja ma pełny kontekst bez tego wątku.

---

## 1. Po co ten projekt

Dowód dopasowania + nauka end-to-end pod ofertę **Data Engineer / GenAI-on-data**
(Data Lake, hurtownia, pipeline'y batch/streaming, BigQuery, „chat with data",
NL2SQL, RAG, DevSecOps). Właściciel ma profil **frontend (React/TS) + AI +
Python/FastAPI** — ten projekt jest mostem z tego profilu do roli data-eng.

**Cel:** nauka end-to-end (dotknąć każdej warstwy), nie produkt produkcyjny.

## 2. Kluczowe decyzje (zatwierdzone)

| Temat | Decyzja |
|---|---|
| Dataset | **NYC Taxi** (Parquet, mały wycinek 1–2 miesiące, świadomie pod free tier) |
| Chmura | **Realne GCP na free tier** (BigQuery 1 TB zapytań/mies gratis) |
| Streaming | **Symulowany prawdziwym Pub/Sub** (odtwarzanie pliku, bo taxi nie ma live-feedu) |
| LLM | **Lokalnie przez Ollama = zero kosztów LLM.** `gemma4:latest` (główny NL2SQL), `llama3.1:8b` (porównanie w ewaluacji), `nomic-embed-text` (embeddingi RAG) |
| Baza wektorowa | **Chroma** lokalnie (pgvector jako opcja later) |
| Orkiestracja | **Airflow lokalnie w Dockerze** (NIE Cloud Composer — poza free tier) |
| Model hurtowni | **Pełny star schema** (fakty + 4 wymiary) |
| Zakres RAG | RAG na schemacie (wektory opisów + few-shot). **Neo4j/graf = świadoma faza 2** |
| Front | **Minimalny** (React lub HTML+fetch) — ma pokazać spięcie w produkt, nie być projektem frontendowym |

## 3. Architektura ogólna — 4 bloki

```
[1] Ingestion   →   [2] Warehouse   →   [3] GenAI          →   [4] Interfejs
batch+streaming     BigQuery/dbt         chat with data          FastAPI + mini-front
                    modelowanie wym.      NL2SQL + RAG            (świadomy wyróżnik)
                    partycje/klastry      guardraile + eval
        orkiestracja: Airflow (lokalnie)  ·  DevSecOps przekrojowo
```

Każdy blok = osobny katalog/moduł z własnym interfejsem i testami.

## 4. Blok [1] — Ingestion (batch + streaming)

**Batch (główna droga):**
```
Parquet (miesięczny) → GCS bucket (Data Lake, warstwa raw) → BigQuery raw.trips
```
- Bucket GCS = warstwa Data Lake (raw), plik surowy bez transformacji.
- Load do `raw.trips` bez transformacji (te robi dbt w [2]).
- Uruchamiane przez Airflow DAG: pobierz → GCS → load do BQ.

**Streaming (symulowany, realnym Pub/Sub):**
```
ten sam Parquet → producent czyta wiersz po wierszu → Pub/Sub topic
    → subskrybent → BigQuery stream.trips
```
- Realny Pub/Sub, dane z odtwarzania pliku z throttlingiem (udają napływ live).
- Osobna tabela `stream.trips` — żeby pogodzić dwie drogi w warstwie mart ([2]).
- Nauka: Pub/Sub, streaming inserts, at-least-once, deduplikacja.

**Dwie osobne tabele świadomie** — realny problem hurtowni „offline + online".

**DevSecOps tu:** klucz GCP przez env/Secret Manager (nie w repo), `.gitignore`
na credentiale, walidacja schematu przy load → dead-letter dla brzydkich wierszy.

**Moduły:**
- `ingestion/batch_load.py` — Parquet → GCS → BQ
- `ingestion/stream_producer.py` — odtwarzanie → Pub/Sub
- `ingestion/stream_consumer.py` — Pub/Sub → BQ
- `dags/ingestion_dag.py` — orkiestracja batcha

## 5. Blok [2] — Warehouse (BigQuery + dbt) — RDZEŃ OFERTY

**Warstwy (medallion):**
```
raw.trips + stream.trips → staging (czyszczenie, typy, dedup) → marts (star schema)
                    wszystko w BigQuery, transformacje przez dbt
```

**STAGING (`stg_trips`):** scala raw+stream, **deduplikuje**, czyści (odrzuca
ujemne kwoty, zerowy dystans, błędne daty), ujednolica typy/strefy czasowe.

**MARTS — star schema:**
```
dim_datetime, dim_location, dim_ratecode, dim_payment  →  fct_trips
                                          (miary: kwota, napiwek, dystans, czas)
```
To „modelowanie logiczne i fizyczne" + „hurtownia" z oferty. Na rozmowie padnie.

**Optymalizacja fizyczna (wymaganie „optymalizacja SQL w BQ"):**
- **Partycjonowanie** `fct_trips` po `pickup_date` (zapytania czasowe skanują mniej).
- **Klasteryzacja** po `location_id`.
- **Zmierz GB przed/po** — konkretny dowód na rozmowę („skan z X GB do Y GB").

**dbt** (standard transformacji): wersjonowanie, testy danych (`not_null`,
`unique`, `relationships`) = warstwa governance/jakości, dokumentacja + graf.

**Powiązanie z [3]:** opisy kolumn w `dbt/models/schema.yml` staną się źródłem
wiedzy dla RAG (LLM z nich rozumie kolumny). Warstwy się zazębiają.

**Moduły:**
- `dbt/models/staging/stg_trips.sql`
- `dbt/models/marts/dim_*.sql`, `fct_trips.sql`
- `dbt/models/schema.yml` (testy + opisy → zasilą RAG)
- DAG Airflow: po ingestion → `dbt run` + `dbt test`

## 6. Blok [3] — GenAI „chat with data" (most z profilu właściciela)

**Przepływ jednego pytania:**
```
pytanie użytkownika
  [1] RAG: nomic-embed → wyszukaj kontekst schematu + few-shot (źródło: schema.yml)
  [2] NL2SQL: gemma4 generuje SQL (pytanie + schemat + przykłady)
  [3] GUARDRAILE: walidacja PRZED wykonaniem ← „ograniczanie ryzyk NL2SQL"
        - tylko SELECT (blok DROP/DELETE/UPDATE)
        - allowlista tabel/kolumn
        - wymuszony LIMIT + dry-run BQ (ile GB? odrzuć za drogie → chroni free tier)
  [4] Wykonanie na BigQuery → wyniki
  [5] LLM streszcza wynik po ludzku + pokazuje użyty SQL
```

**RAG:** Chroma + nomic-embed. Indeks: opisy tabel/kolumn ze `schema.yml`,
słownik wartości, few-shot pytanie→poprawny SQL (podnoszą trafność słabszego modelu).

**Guardraile (`genai/guardrails.py`) — najmocniejszy element pod ofertę:**
parsowanie SQL, tylko SELECT, allowlista, wymuszony LIMIT, **dry-run BQ** (BQ
podaje ile GB *zeskanowałoby* bez wykonania) → blok zbyt drogich. To realizuje
„ograniczanie ryzyk" jako kod, nie hasło.

**Ewaluacja (`genai/eval.py`) — „ocena jakości systemów GenAI":**
~15–20 pytań testowych ze złotą prawdą (oczekiwany SQL/wynik). Metryki: czy SQL
się wykonał, zgodność z oczekiwanym, ile guardraile odrzuciły. **Porównanie
gemma4 vs llama3.1** → tabelka trafności = gotowy materiał na rozmowę.

**Abstrakcja `genai/llm_client.py`:** jeden interfejs, backend `ollama` domyślny
(gemma4/llama3.1) + opcjonalnie chmurowy. Przełączenie = config.

**Moduły:** `llm_client.py`, `retriever.py`, `nl2sql.py`, `guardrails.py`, `eval.py`
(wszystkie w `genai/`).

**Faza 2 (świadomie odłożone):** Neo4j — relacje tabel jako graf schematu
(nice-to-have w ofercie); pgvector zamiast Chroma (SQL-owy wariant bazy wektorowej).

## 7. Blok [4] — Interfejs (świadomy wyróżnik) + DevSecOps

**FastAPI (`api/main.py`):**
```
POST /chat  {question} → RAG→NL2SQL→guardraile→BQ → {answer, sql, rows, scanned_gb, model}
GET  /health → status BQ + Ollama
GET  /eval   → wynik ostatniej ewaluacji (tabelka modeli)
```
Zwracamy też **użyty SQL + zeskanowane GB** = transparentność i dowód działania
guardraili/optymalizacji.

**Front (minimalny, świadomie):** jeden ekran — pole pytania → odpowiedź +
rozwijany SQL + tabela wyników + „model, GB". React (rdzeń właściciela) lub
HTML+fetch. Zakres celowo mały.

**DevSecOps przekrojowo:**
- Sekrety przez env/`.env` w `.gitignore`, nigdy w repo.
- CI/CD: GitHub Actions — ruff (lint), pytest, `dbt test`, gitleaks (skan sekretów).
- `docker-compose` spina Airflow + Ollama + API lokalnie.
- Guardraile [3] = też element bezpieczeństwa (walidacja wejścia LLM).

## 8. Kolejność budowy (zawsze coś działającego)

```
Faza 0  Setup: repo, docker-compose, GCP projekt + free tier, .env
Faza 1  [1] batch: Parquet → GCS → BQ raw            (pierwszy realny load)
Faza 2  [2]: dbt staging → star schema → partycje/klastry
Faza 3  [3]: RAG + NL2SQL + guardraile na gotowej hurtowni
Faza 4  [1] streaming: Pub/Sub producent/konsument
Faza 5  [4]: FastAPI + front
Faza 6  Ewaluacja + porównanie modeli + Airflow spina batch+dbt
Faza 7  DevSecOps: CI/CD, skan sekretów, dopięcie
```
Streaming celowo PO batchu i hurtowni — najpierw miej z czego pytać.

## 9. Struktura katalogów

```
taxi-chat-data/
├── ingestion/          [1] batch_load.py, stream_producer.py, stream_consumer.py
├── dbt/                [2] models/staging, models/marts, schema.yml
├── genai/             [3] llm_client, retriever, nl2sql, guardrails, eval
├── api/               [4] main.py (FastAPI)
├── frontend/          [4] mini-UI
├── dags/              Airflow DAG-i
├── tests/             pytest
├── docker-compose.yml Airflow + Ollama + API
├── .github/workflows/ci.yml
├── .env.example
└── README.md          opis + MAPA na wymagania oferty (kluczowe dla recenzenta)
```

## 10. Mapa na wymagania oferty (do README)

| Wymaganie oferty | Gdzie w projekcie |
|---|---|
| Pipeline batch + streaming | Blok [1] (GCS→BQ + Pub/Sub) |
| Data Lake + hurtownia | Blok [1] GCS raw + Blok [2] star schema |
| Modelowanie logiczne/fizyczne | Blok [2] dim/fct + partycje/klastry |
| Optymalizacja SQL w BQ | Blok [2] partycjonowanie/klasteryzacja + pomiar GB |
| LLM/GenAI, chat with data | Blok [3] cały |
| NL2SQL + ograniczanie ryzyk | Blok [3] nl2sql + guardrails |
| RAG + bazy wektorowe | Blok [3] retriever + Chroma |
| Ocena jakości GenAI | Blok [3] eval (gemma4 vs llama3.1) |
| DevSecOps | Sekrety + CI/CD + docker + guardraile |
| Python advanced | Całość |
| Pub/Sub, GCP | Blok [1], BigQuery |
| Neo4j / graf (nice-to-have) | Faza 2 (odłożone świadomie) |

## 11. Zasady / uwagi

- **Koszt:** jedyny realny koszt = BigQuery, w ramach free tier (1 TB/mies).
  Guardraile z dry-run dodatkowo chronią przed przekroczeniem. LLM = 0 zł (Ollama).
- Zainstalowane modele Ollama (potwierdzone): `gemma4:latest`, `llama3.1:8b`,
  `nomic-embed-text:latest`.
- Wycinek danych mały świadomie — skaluj dopiero gdy całość działa.
- Neo4j i pgvector = faza 2, nie blokują MVP.
