# Task 4: Batch load Parquet → GCS → BigQuery raw — notatka do nauki

## Co zrobiliśmy

Zbudowaliśmy moduł `ingestion/batch_load.py`, który spina lokalny plik
Parquet (pobrany w Task 3 przez `download_taxi_parquet`) z docelowym
środowiskiem w Google Cloud. Pipeline składa się z czterech kroków, każdy w
osobnej, testowalnej funkcji: `ensure_bucket(cfg)` tworzy bucket GCS
(warstwa `raw/`), jeśli jeszcze nie istnieje; `upload_to_gcs(cfg, local_path)`
wgrywa plik pod ścieżkę `raw/<nazwa_pliku>` i zwraca URI w formacie
`gs://...`; `ensure_dataset(cfg)` tworzy dataset `raw` w BigQuery, jeśli
jeszcze nie istnieje; `load_gcs_to_bq(cfg, gcs_uri)` uruchamia load job,
który czyta Parquet z GCS i ładuje go do tabeli `raw.trips`, a na końcu
zwraca liczbę załadowanych wierszy. Funkcja `run_batch(cfg, local_path)`
spina to wszystko w jedno wywołanie. Osobno wydzieliliśmy czystą funkcję
pomocniczą `blob_name_for(local_path) -> str`, która tylko oblicza nazwę
obiektu w buckecie (`raw/` + nazwa pliku) — bez żadnych efektów ubocznych.

Pisaliśmy to metodą TDD: najpierw `tests/test_batch_load.py` z testem
`test_blob_name_for_strips_directory` (czysta funkcja) oraz testem
oznaczonym `@pytest.mark.integration`, uruchamianym tylko ręcznie. Test
w wersji RED zakończył się `ModuleNotFoundError: No module named
'ingestion.batch_load'`, a integracyjny test był w tym momencie w ogóle
niewidoczny dla testera (deselekcja przez `addopts = -m "not integration"`
w `pytest.ini`, zanim jeszcze doszło do kolekcji błędu). Po napisaniu
implementacji unit-test przeszedł na zielono (1 passed, 1 deselected).
Na końcu odpaliliśmy ręcznie prawdziwy smoke-test: utworzenie buckecie
`taxi-chat-data-taxi-lake`, wgranie ~45 MB pliku Parquet, utworzenie
datasetu `raw` i load job do `raw.trips`. W praktyce napotkaliśmy realny
problem sieciowy — domyślny timeout klienta GCS (60 s na pojedynczy
request) był za krótki na wolne łącze wysyłkowe tej maszyny, więc
podnieśliśmy timeout `upload_from_filename(..., timeout=600)`. Po tej
poprawce test integracyjny przeszedł, a `bq query` niezależnie potwierdził
3 066 766 wierszy w `raw.trips` — zgodnie z oczekiwaną skalą dla stycznia
2023.

## Dlaczego takie decyzje

**GCS jako warstwa raw Data Lake, a nie bezpośredni load do BigQuery.**
Moglibyśmy teoretycznie załadować Parquet z dysku lokalnego wprost do
BigQuery, ale trzymanie surowego pliku w GCS pod prefiksem `raw/` to
świadome zastosowanie architektury **medallion** (raw → staging/silver →
mart/gold), popularnej w nowoczesnym data engineeringu. GCS pełni tu rolę
Data Lake: tania, trwała, niezmienna kopia danych źródłowych w ich
oryginalnym formacie, niezależna od żadnego silnika zapytań. Dzięki temu
zawsze możemy odtworzyć dowolny load job w BigQuery bez ponownego
pobierania danych ze źródła (NYC TLC), a inne narzędzia (Spark, Dataflow,
inny warehouse) też mogą po nie sięgnąć.

**Ładowanie surowe, bez transformacji — te przyjdą później w dbt (Faza 2).**
`load_gcs_to_bq` celowo nie filtruje, nie czyści i nie przekształca danych.
Tabela `raw.trips` ma wyglądać dokładnie tak jak plik źródłowy — to jest
właśnie warstwa "raw" w ELT (Extract-Load-**T**ransform, w odróżnieniu od
starszego ETL, gdzie transformacja dzieje się przed załadowaniem).
Nowoczesne stosy danych (BigQuery + dbt to kanoniczny przykład) ładują
surowe dane jak najszybciej i jak najprościej, a całą logikę biznesową —
czyszczenie, deduplikację, wyliczanie kolumn — przenoszą do warstwy
transformacji (dbt models), gdzie jest ona wersjonowana, testowalna i
łatwa do zmiany bez re-ingestii danych.

**Autodetekcja schematu (`autodetect=True`).** Zamiast ręcznie definiować
schemat tabeli (dziesiątki kolumn NYC Taxi), pozwalamy BigQuery odczytać
schemat wprost z metadanych pliku Parquet. Parquet, w przeciwieństwie do
CSV, przechowuje typy kolumn w swoich metadanych, więc autodetekcja jest tu
w pełni wiarygodna — to kolejny argument za wyborem tego formatu w Task 3.

**`WRITE_TRUNCATE` dla idempotentnych powtórzeń.** Pipeline ingestii będzie
uruchamiany wielokrotnie podczas nauki, debugowania i przy okazji zmian w
kodzie. `WRITE_TRUNCATE` sprawia, że każde uruchomienie load joba nadpisuje
całą zawartość tabeli, zamiast dokładać duplikaty przy każdym powtórzeniu
(jak zrobiłby to `WRITE_APPEND`). To ta sama zasada idempotencji, którą
zastosowaliśmy w Task 3 przy pobieraniu pliku — kluczowa właściwość
dobrze zaprojektowanych kroków pipeline'u danych.

**Brak mockowania klientów chmurowych w unit-testach.** Świadomie
zrezygnowaliśmy z mockowania `google.cloud.storage.Client` i
`google.cloud.bigquery.Client`. Mock tych klientów zastąpiłby całą logikę
biznesową (tworzenie buckecia, upload, load job) atrapami, które nic nie
sprawdzają poza tym, że wywołaliśmy odpowiednie metody z odpowiednimi
argumentami — co daje fałszywe poczucie bezpieczeństwa, bo prawdziwe API
Google Cloud ma dziesiątki subtelnych zachowań (limity, uprawnienia,
formaty odpowiedzi), których żaden mock nie odda wiernie. Zamiast tego:
jedyna czysta logika (`blob_name_for`) dostaje prawdziwy, szybki unit-test,
a cała reszta — kod, który faktycznie rozmawia z chmurą — jest sprawdzana
przez ręczny **integration smoke-test**, uruchamiany świadomie, poza
domyślnym przebiegiem `pytest` (marker `integration` wykluczony w
`pytest.ini` przez `addopts = -m "not integration"`). To przykład zasady
"testuj na właściwym poziomie": logikę czystą testuj szybkimi unit-testami,
a integrację z zewnętrznym systemem — testem integracyjnym, który faktycznie
tę integrację wykonuje, zamiast ją symulować.

**ADC (Application Default Credentials) zamiast pliku klucza service
account.** Do autoryzacji używamy `gcloud auth application-default login`
zamiast pobierania i przechowywania pliku JSON z kluczem service accountu.
Plik klucza to długożyjący sekret, który łatwo przypadkowo scommitować do
repozytorium albo zostawić na dysku bez rotacji. ADC opiera się o krótkotrwałe
tokeny powiązane z tożsamością zalogowanego użytkownika (albo, w środowisku
produkcyjnym, z tożsamością maszyny/service accountu przypisanego do zasobu
compute), więc nie ma żadnego sekretu do wycieku z poziomu kodu czy repo.

## Jakiej koncepcji to uczy

To wprowadzenie do klasycznego kroku **load** w architekturze ELT oraz do
rozróżnienia **Data Lake vs Data Warehouse**: GCS (Lake) przechowuje surowe,
niezmienne dane w oryginalnym formacie i jest tani w utrzymaniu, a BigQuery
(Warehouse) przechowuje dane zorganizowane w tabele, zoptymalizowane pod
zapytania SQL. Warstwa `raw/` w buckecie i tabela `raw.trips` w BigQuery to
najniższy poziom architektury **medallion** — w Fazie 2 dojdą kolejne
warstwy (staging, marts) budowane przez dbt na bazie tej surowej tabeli, bez
konieczności ponownego dotykania źródła danych. **Load job** w BigQuery
(`client.load_table_from_uri`) to podstawowy mechanizm masowego wczytywania
danych — asynchroniczna operacja, na którą czekamy przez `load_job.result()`,
analogiczna do `COPY` w Redshift czy `bq load` w CLI. Wreszcie, decyzja o
testowaniu na właściwym poziomie (czysta logika = unit-test, integracja z
chmurą = ręczny smoke-test) to wzorzec przenoszący się na każdy prawdziwy
pipeline danych: im więcej kodu dotyka zewnętrznych systemów I/O, tym mniej
sensu ma mockowanie każdego wywołania — lepiej mieć mały zestaw szybkich
testów logiki i osobny, świadomie uruchamiany test integracyjny, który
naprawdę weryfikuje działanie całości.
