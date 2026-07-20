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

## Jak testujemy DAG bez `apache-airflow` w środowisku

Uruchamianie schedulera w teście jednostkowym byłoby wolne i kruche — ale
`import`-owanie DAG-a też wymagałoby `apache-airflow` w interpreterze, a tego
akurat **nie chcemy** (patrz niżej). Dlatego strukturę sprawdzamy **parsując
plik modułem `ast`** (bez importu, bez Airflow): czytamy
`dags/dbt_transform_dag.py` jako drzewo składni i asertujemy fakty o grafie —
`dag_id == "dbt_transform"`, dokładnie dwa zadania (`dbt_run`, `dbt_test`),
krawędź `dbt_run >> dbt_test`, `schedule=None`, `catchup=False`. Samo
`ast.parse` wyłapuje błędy składni; asercje — zmianę nazwy symbolu, zgubioną
zależność czy zmieniony harmonogram. To wszystko działa w **głównym `.venv`**,
więc `pytest` przechodzi na zielono bez żadnych skip-ów ani osobnego środowiska.

Że plik **naprawdę** importuje się i działa jako DAG Airflow, dowodzi dopiero
`docker compose ... up` + trigger (krok operatora) — to silniejszy test niż
import w venv (realnie wykonuje zadania na BigQuery), więc nie dublujemy go.

## Dlaczego `apache-airflow` NIE trafia do wspólnego `.venv`

Kuszące byłoby dołożyć airflow do głównego `.venv` i zrobić klasyczny test
import-owy. Nie robimy tego — dwa powody, oba zweryfikowane `pip install
--dry-run`:

1. Główny `.venv` to **Python 3.14**; `apache-airflow` 2.10.x wymaga `<3.13` —
   po prostu się nie zainstaluje.
2. Wersja Airflow, która wspiera 3.14 (3.x), przy instalacji do wspólnego venva
   **zdegradowałaby `fastapi`** (0.139 → 0.136) i pociągnęła ~70 ciężkich
   zależności — złamałoby to pracę peera nad API. Wspólny venv to współdzielony
   stan; nie mutujemy go w locie.

Stąd test na `ast` (zero zależności) + żywy run jako realny dowód importu.
Airflow **nie** trafia do `requirements.txt` — kontener ma własny runtime.

## Najważniejsze do zapamiętania

- DAG = graf zadań; operator = typ zadania; `>>` = zależność.
- `schedule=None` + `catchup=False` = ręczny, jednorazowy trigger.
- ADC montowany read-only = kontener uwierzytelnia się jako Ty, bez kluczy.
- Strukturę DAG-a można sprawdzić parsując plik (`ast`), bez importu Airflow.
- Ciężkie zależności dev-only trzymaj poza wspólnym środowiskiem; realny import
  weryfikuj żywym runem, nie dokładaniem paczki do współdzielonego venv.
