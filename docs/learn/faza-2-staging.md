# Faza 2: warstwa staging (`stg_trips`)

## Co robi staging

Model `stg_trips` to pierwsza transformacja nad surowymi danymi (`raw.trips`
z Fazy 1). Warstwa staging w klasycznym podejściu ELT (silver/staging layer)
odpowiada za:

1. **Czyszczenie (clean)** — odrzucenie wierszy, które są ewidentnie błędne:
   ujemne kwoty (`fare_amount`, `total_amount`), niedodatni dystans
   (`trip_distance <= 0`), czasowo niespójne przejazdy (`dropoff < pickup`),
   przejazdy z datą sprzed istnienia TLC (`< 2009-01-01`) lub z datą w
   przyszłości względem `current_timestamp()`.
2. **Rzutowanie typów (cast)** — surowe dane z Parquet mają kolumny takie jak
   `passenger_count` czy `RatecodeID` jako FLOAT (bo Parquet/BigQuery
   auto-inferuje typ z NULL-i w danych), a semantycznie są to liczby całkowite.
   Rzutujemy je na `INT64`.
3. **Zmianę nazw (rename)** — z CamelCase (`VendorID`, `PULocationID`) na
   snake_case (`vendor_id`, `pickup_location_id`), zgodnie z konwencją
   warstwy staging/marts w dbt.
4. **Deduplikację (dedup)** — przez `QUALIFY ROW_NUMBER() OVER (PARTITION BY
   trip_key ORDER BY pickup_datetime) = 1`.
5. **Nadanie surogatnego klucza (surrogate key)** — `trip_key` liczony jako
   deterministyczny hash (`dbt_utils.generate_surrogate_key`) po kolumnach
   identyfikujących przejazd.

Dodatkowo model wylicza dwie kolumny pochodne: `pickup_date` (data, przyszły
klucz partycjonowania w `fct_trips`) oraz `trip_duration_min` (różnica
`dropoff_datetime - pickup_datetime` w minutach, przez `TIMESTAMP_DIFF`).

## Dlaczego deterministyczny hash jako klucz

`trip_key` nie jest losowym UUID, tylko hashem (SHA-256 przez
`dbt_utils.generate_surrogate_key`) policzonym z kolumn: pickup/dropoff
datetime, PU/DO location, fare_amount, vendor_id. Dzięki temu:

- **Ten sam przejazd zawsze dostaje ten sam klucz** — jeśli źródłowe dane
  się nie zmieniły, przebudowanie modelu (`dbt build`) da identyczny
  `trip_key`. To pozwala na `QUALIFY ROW_NUMBER() ... = 1` — dedup działa,
  bo duplikaty (te same wartości źródłowe) hashują się na ten sam klucz i
  wygrywa jeden wiersz wg `ORDER BY pickup_datetime`.
- **Przygotowanie pod Fazę 4** — kiedy dojdzie strumień (streaming ingestion),
  te same przejazdy mogą pojawić się zarówno w danych wsadowych (batch,
  Faza 1), jak i w strumieniu. Deterministyczny klucz policzony z tych
  samych kolumn źródłowych pozwoli rozpoznać "to jest ten sam przejazd" i
  zrekoncyliować (reconcile) dane z obu źródeł bez dodatkowego mapowania.

Alternatywą byłby `GENERATE_UUID()` przy każdym uruchomieniu — ale wtedy
klucz zmieniałby się przy każdym rebuildzie i nie dawałby żadnej gwarancji
idempotencji ani możliwości łączenia z innym źródłem.

## Dlaczego filtrujemy złe wiersze zamiast dead-letter

W tym projekcie (jeden batch, jedno źródło, brak wymogu audytu odrzuconych
rekordów) prostsze i tańsze jest odrzucenie złych wierszy bezpośrednio w
klauzuli `WHERE` warstwy staging, niż budowanie osobnej tabeli
dead-letter/quarantine. Dead-letter ma sens, gdy:

- trzeba wiedzieć *ile* i *jakich* rekordów odrzucono (compliance, SLA),
- dane napływają ciągle (streaming) i błędne rekordy trzeba osobno
  monitorować/naprawiać,
- odrzucone rekordy mają wartość biznesową do ręcznej analizy.

Tutaj żadne z tych kryteriów nie jest priorytetem Fazy 2 — świadomie
wybieramy prostotę. Konsekwencja: `stg_trips` ma mniej wierszy niż
`raw.trips`, i to jest oczekiwane (patrz sekcja z liczbami niżej).

## Dlaczego staging jest widokiem (VIEW), nie tabelą

`stg_trips` materializuje się jako `view` (ustawione zarówno w
`dbt_project.yml` dla całego folderu `staging`, jak i w `config()` samego
modelu — redundancja celowa, dokumentuje intencję lokalnie w pliku). Zalety:

- **Zawsze świeże dane** — widok nie przechowuje własnej kopii danych,
  więc każde zapytanie do `stg_trips` czyta na żywo z `raw.trips`. Nie ma
  ryzyka, że warstwa staging "zamrozi" stare dane po doładowaniu source'a.
- **Zero dodatkowego storage** — BigQuery nie kopiuje ~3 mln wierszy do
  nowej tabeli; widok to tylko zapisany SQL.
- Koszt: każde odpytanie widoku ponownie liczy cały SELECT (skanuje
  `raw.trips`). Dla warstwy staging, która jest "przejściowa" (surowe dane →
  wymiary/fakty), to akceptowalny kompromis — kolejne warstwy (marts) są
  już materializowane jako tabele, bo tam liczy się szybkość odczytu przez
  konsumentów (dashboardy, chat).

## Kluczowe pojęcia

- **Warstwa staging (silver layer)** — pośredni etap w architekturze
  medalionowej (bronze/raw → silver/staging → gold/marts): dane oczyszczone
  i ujednolicone nazewniczo, ale jeszcze nieagregowane biznesowo.
- **Surrogate key** — sztuczny klucz (nie pochodzący wprost z systemu
  źródłowego jako natural key), tu wygenerowany deterministycznie z hasha,
  używany do identyfikacji rekordu i joinów w dalszych warstwach.
- **`QUALIFY`** — klauzula BigQuery (i part Snowflake/inne) pozwalająca
  filtrować po wyniku funkcji okienkowej (window function) bez
  opakowywania zapytania w dodatkowy `SELECT ... FROM (...) WHERE rn = 1`.
  Tu użyta do dedupu: zostaje jeden wiersz na `trip_key`.
- **Data cleaning w ELT** — w przeciwieństwie do ETL (transformacja przed
  załadowaniem), w ELT ładujemy surowe dane od razu (Faza 1: `raw.trips`),
  a czyszczenie/transformację robimy już w warehouse, w SQL, warstwa po
  warstwie (staging → marts). Łatwiej debugować i re-run'ować pojedyncze
  etapy.

## Wynik (dowód działania)

`docker compose run --rm dbt build --select stg_trips` — widok zbudowany,
5 testów danych PASS (w tym `unique` na `trip_key`, co dowodzi że dedup
faktycznie działa — gdyby `QUALIFY ROW_NUMBER() ... = 1` nie eliminował
duplikatów, ten test by failował).

Liczba wierszy w `staging.stg_trips`: **2 998 748**, wobec **3 066 766** w
`raw.trips` — odfiltrowano **68 018** wierszy (ok. 2.2%) jako niepoprawne
dane źródłowe.
