# Faza 6 — Airflow: orkiestracja transformacji dbt (lokalny Docker)

Notatka do nauki (PL). Kod, komentarze i nazwy — po angielsku; ta notatka
tłumaczy „dlaczego”.

## Po co nam Airflow tutaj

Mamy działający potok: surowe dane → `dbt run` (staging + marts) → `dbt test`.
Do tej pory odpalaliśmy dbt ręcznie. **Airflow** to orkiestrator: opisujemy
zależności między krokami jako graf i pozwalamy schedulerowi je wykonać,
zebrać logi, pokazać status (zielony/czerwony) i ewentualnie ponowić.

W tym zadaniu robimy celowo **minimalny** DAG: dwa kroki, ręczny trigger, bez
crona i bez Cloud Composera (zasada YAGNI). Chodzi o pokazanie wzorca
orkiestracji nad istniejącym projektem dbt, nie o produkcyjny scheduler.

## DAG i operatory — pojęcia

- **DAG** (Directed Acyclic Graph) — graf zadań bez cykli. Jeden plik `.py`
  w katalogu `dags/` definiuje jeden (lub więcej) DAG. Airflow skanuje ten
  katalog i „odkrywa” DAG przez zaimportowanie modułu.
- **Operator** — klasa opisująca *jeden typ* zadania. `BashOperator` uruchamia
  polecenie powłoki. Instancja operatora (`task_id="dbt_run"`) to konkretne
  zadanie w grafie.
- **Zależność** `dbt_run >> dbt_test` — „run przed test”. To przeciążony
  operator `>>` (bitshift), który Airflow interpretuje jako krawędź w grafie.
- `schedule=None` — DAG **nie** ma harmonogramu; uruchamiasz go ręcznie
  (UI albo `airflow dags trigger`). `catchup=False` — nie „nadrabiamy”
  zaległych przebiegów z przeszłości (istotne, gdyby był harmonogram).

## Dlaczego `BashOperator` + dbt, a nie plugin dbt-airflow

Istnieją integracje (np. `astronomer-cosmos`), które rozbijają każdy model dbt
na osobne zadanie Airflow. To potężne, ale ciężkie. Na start `dbt run` i
`dbt test` jako dwa `BashOperator`y są przezroczyste: dokładnie te same
polecenia, które puszczamy lokalnie, tyle że orkiestrowane. Łatwo debugować,
zero dodatkowej warstwy magii.

## Jak ADC trafia do kontenera (i czemu read-only)

dbt-bigquery uwierzytelnia się przez **ADC** (Application Default Credentials).
Lokalnie plik leży w `~/.config/gcloud/application_default_credentials.json`.
W compose montujemy **tylko ten plik**, **read-only** (`:ro`), pod ścieżkę w
kontenerze i wskazujemy na niego `GOOGLE_APPLICATION_CREDENTIALS`. Dzięki temu:

- kontener działa jako *Ty* (te same uprawnienia do BigQuery),
- nie tworzymy ani nie kopiujemy kluczy service-account (mniejsze ryzyko
  wycieku),
- `:ro` gwarantuje, że proces w kontenerze nie nadpisze/uszkodzi Twoich
  poświadczeń.

To ten sam sprawdzony wzorzec, co w Fazie 2 dla samego dbt.

## Jak testujemy DAG bez stawiania Airflow

Uruchamianie schedulera w teście jednostkowym byłoby wolne i kruche. Zamiast
tego **testujemy strukturę przez import**: ładujemy `dags/dbt_transform_dag.py`
jako moduł i sprawdzamy fakty o grafie — `dag_id`, dokładnie dwa zadania
(`dbt_run`, `dbt_test`), krawędź `dbt_run >> dbt_test`, `schedule_interval is
None`, `catchup is False`. Żadnego żywego Airflow, żadnego BigQuery. Realny
przebieg end-to-end weryfikuje dopiero `docker compose ... up` (krok operatora).

## Gdzie mieszka `apache-airflow` — i dlaczego NIE we wspólnym `.venv`

Import-test potrzebuje `apache-airflow`, ale **nie** dokładamy go do głównego,
współdzielonego `.venv`. Dwa powody, oba zweryfikowane `pip install --dry-run`:

1. Główny `.venv` to **Python 3.14**; `apache-airflow` 2.10.x wymaga `<3.13` —
   po prostu się nie zainstaluje.
2. Wersja Airflow, która wspiera 3.14 (3.3.x), przy instalacji do wspólnego
   venva **zdegradowałaby `fastapi`** (0.139 → 0.136) i pociągnęła ~70 ciężkich
   zależności — złamałoby to pracę peera nad API. Wspólny venv to współdzielony
   stan; nie mutujemy go w locie.

Rozwiązanie: **izolowany** `.venv-airflow` (python3.11, `apache-airflow==2.10.4`
— dokładnie wersja z obrazu kontenera). Struktura-test przechodzi tam na
zielono, a w głównym `.venv` używamy `pytest.importorskip("airflow")`, więc
zadanie **pomija się** (skip), a cały pakiet testów zostaje zielony. Airflow
**nie** trafia do `requirements.txt` — to ciężka zależność wyłącznie dev/test.

## Najważniejsze do zapamiętania

- DAG = graf zadań; operator = typ zadania; `>>` = zależność.
- `schedule=None` + `catchup=False` = ręczny, jednorazowy trigger.
- ADC montowany read-only = kontener uwierzytelnia się jako Ty, bez kluczy.
- Strukturę DAG-a testuje się przez import, nie przez stawianie schedulera.
- Ciężkie zależności dev-only trzymaj poza wspólnym środowiskiem.
