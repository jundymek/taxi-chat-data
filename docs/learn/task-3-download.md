# Task 3: Pobieranie Parquet NYC Taxi — notatka do nauki

## Co zrobiliśmy

Zbudowaliśmy moduł `ingestion/download.py`, który odpowiada za pobranie
miesięcznego pliku Parquet z publicznego data lake NYC TLC (Taxi & Limousine
Commission). Moduł udostępnia dwie funkcje: `build_taxi_url(month: str) -> str`,
która czysto składa URL do pliku (np. `yellow_tripdata_2023-01.parquet`) ze
stałego prefiksu `BASE_URL`, oraz `download_taxi_parquet(cfg: Config) -> str`,
która korzysta z `Config` (Task 2), sprawdza, czy plik już istnieje lokalnie w
`cfg.data_dir`, i albo zwraca istniejącą ścieżkę bez żadnego ruchu sieciowego,
albo pobiera plik strumieniowo (`requests.get(..., stream=True)`) w kawałkach
po 1 MB i zapisuje go na dysk. Pisaliśmy to metodą TDD: najpierw
`tests/test_download.py` z dwoma testami — `test_build_taxi_url` (czysta
funkcja, żadnych efektów ubocznych) i `test_download_skips_if_exists`, który za
pomocą `monkeypatch` podmienia `requests.get` na funkcję rzucającą wyjątek, co
udowadnia, że gdy plik już istnieje, kod w ogóle nie próbuje sięgać do sieci.
Najpierw uruchomiliśmy testy i zobaczyliśmy czerwony wynik
(`ModuleNotFoundError: No module named 'ingestion.download'`), potem
napisaliśmy minimalną implementację, po której oba testy przeszły, a na końcu
wykonaliśmy prawdziwy smoke test — realne pobranie ~45 MB pliku z CloudFront.

## Dlaczego takie decyzje

**Rozdzielenie "pobierania źródła" od "ładowania danych".** `download.py` ma
jedną odpowiedzialność: dostarczyć plik Parquet na lokalny dysk. Nie parsuje
go, nie waliduje schematu, nie wrzuca do BigQery ani GCS — to zadania kolejnych
modułów (`batch_load.py` w następnych taskach). Taki podział na etapy
ekstrakcji (extract) i ładowania (load) to klasyczny wzorzec ETL/ELT: każdy
krok pipeline'u da się przetestować, uruchomić i debugować osobno, a błąd w
jednym etapie nie zatruwa logiki drugiego.

**Idempotencja przez sprawdzenie `os.path.exists`.** Plik ma ~45-50 MB, a
pipeline ingestii będzie uruchamiany wielokrotnie podczas nauki i debugowania.
Bez sprawdzenia istnienia pliku każde ponowne uruchomienie pobierałoby te same
dane od nowa — marnując czas, transfer i (w środowisku produkcyjnym) pieniądze
za egress. Idempotencja — właściwość, że wielokrotne wykonanie tej samej
operacji daje ten sam efekt co jednokrotne — jest fundamentalną cechą
dobrze zaprojektowanych kroków pipeline'u danych: pozwala bezpiecznie
restartować pipeline po awarii bez ręcznego sprzątania.

**Test dowodzący idempotencji przez `monkeypatch` na `requests.get`.** Zamiast
tylko sprawdzić, że funkcja zwraca poprawną ścieżkę, test aktywnie *zabrania*
wywołania sieci — jeśli implementacja kiedykolwiek przestanie sprawdzać
istnienie pliku przed pobraniem, test natychmiast to wykryje przez
`AssertionError`. To przykład testowania zachowania (behavior), a nie tylko
wartości zwracanej — mocniejsza gwarancja niż sam `assert path == existing`.

**Strumieniowe pobieranie (`stream=True`, `iter_content`).** Plik ma dziesiątki
megabajtów, więc wczytanie całej odpowiedzi HTTP do pamięci naraz
(`requests.get(url).content`) byłoby marnotrawstwem RAM-u i nie skalowałoby się
do większych plików (pełne miesiące NYC Taxi bywają grubo ponad 100 MB). Zamiast
tego czytamy odpowiedź w kawałkach po 1 MB i zapisujemy każdy kawałek od razu
na dysk — pamięć procesu zostaje stała niezależnie od rozmiaru pliku.

## Jakiej koncepcji to uczy

To wprowadzenie do klasycznego kroku **ekstrakcji (extract)** w architekturze
ETL/ELT: dane wejściowe pochodzą z zewnętrznego, publicznego data lake (NYC TLC
publikuje otwarte dane o przejazdach taksówek jako pliki Parquet pod stałymi
URL-ami), a nasze zadanie to niezawodnie i powtarzalnie sprowadzić je do
własnej infrastruktury, zanim zaczniemy je przetwarzać. Dwie idee przenoszą się
wprost na dużo większe systemy danych: **idempotentne kroki pipeline'u**
(Airflow, dbt i podobne narzędzia orkiestracji wprost zakładają, że zadania
mogą być ponawiane i powinny wykrywać już wykonaną pracę) oraz **strumieniowe
I/O** (ta sama technika — czytanie i zapisywanie danych w kawałkach zamiast
ładowania całości do pamięci — leży u podstaw działania narzędzi takich jak
`pandas.read_csv(chunksize=...)`, Apache Beam czy Spark, które przetwarzają
dane większe niż dostępny RAM). Wybór formatu Parquet (kolumnowy, skompresowany,
z zapisanym schematem) zamiast np. CSV to też świadoma decyzja inżynierska —
Parquet jest szybszy do odczytu selektywnych kolumn i mniejszy na dysku, co
w kolejnych taskach (ładowanie do BigQuery) będzie miało bezpośredni wpływ na
koszt i wydajność.
