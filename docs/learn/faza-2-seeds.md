# Faza 2 / Task 2: Seedy dbt — słowniki lokalizacji, płatności i taryf — notatka do nauki

## Co zrobiliśmy

Dodaliśmy trzy pliki CSV do `dbt/seeds/`:

- `taxi_zone_lookup.csv` — oficjalny słownik stref NYC TLC (pobrany z
  `d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv`), 265 wierszy
  (`location_id` 1–265) mapujących identyfikator strefy na dzielnicę
  (`borough`), nazwę strefy (`zone`) i strefę usługową (`service_zone`).
  Nagłówek źródłowy (`LocationID,Borough,Zone,service_zone`) znormalizowaliśmy
  do snake_case, nie ruszając samych wierszy (część wartości `zone` zawiera
  przecinki w cudzysłowach, np. `"World Trade Center"` — kopiowane 1:1 ze
  źródła).
- `payment_type_lookup.csv` — 6 wierszy, słownik kodu `payment_type` (1=Credit
  card, 2=Cash, ... 6=Voided trip).
- `ratecode_lookup.csv` — 6 wierszy, słownik kodu `RatecodeID` (1=Standard
  rate, 2=JFK, ... 6=Group ride).

Do tego `_seeds__properties.yml` z jawnymi typami kolumn
(`config.column_types`: INT64/STRING), opisami (`description`) na poziomie
seeda i kolumny klucza, oraz testami `not_null` + `unique` na każdym kluczu
(`location_id`, `payment_type`, `ratecode_id`). Uruchomiliśmy realnie
`docker compose run --rm dbt seed` (3 seedy załadowane do datasetu `marts`,
`taxi_zone_lookup` z 265 wierszami) i `docker compose run --rm dbt test
--select "resource_type:seed"` (6/6 testów PASS), a wynik zweryfikowaliśmy
niezależnie zapytaniem `bq query` — `COUNT(*) = 265`.

## Czym są seedy w dbt

Seed to mały, względnie statyczny zbiór danych referencyjnych, który
utrzymujemy jako plik CSV *w repozytorium kodu* (nie w źródle transakcyjnym) i
ładujemy do hurtowni komendą `dbt seed` (dbt generuje `CREATE TABLE` +
`INSERT` na podstawie zawartości pliku). To co odróżnia seed od zwykłego
modelu: dane nie pochodzą z żadnego zapytania SQL na innej tabeli — pochodzą
wprost z pliku, więc są wersjonowane razem z kodem (widać w `git log`, kiedy i
dlaczego się zmieniły), łatwe do code-review i nie wymagają dodatkowego
pipeline'u ingestion. Typowe zastosowania: słowniki kodów, mapowania kraj→
region, listy świąt, progi konfiguracyjne — dane, które zmieniają się rzadko i
o kolejności wielkości dziesiątek/setek/tysięcy wierszy (nie miliony).

## Po co wzbogacać surowe kody opisami: governance + NL2SQL

Surowe dane przejazdów (`raw.trips` z Fazy 0-1) mają kolumny `payment_type`,
`RatecodeID`, `PULocationID`/`DOLocationID` — same liczby całkowite bez
znaczenia biznesowego. To standardowa praktyka źródeł operacyjnych: kody są
tańsze do przechowywania i stabilne (nie zmieniają się przy tłumaczeniu na
inny język), ale nieczytelne dla człowieka i, co ważniejsze w tym projekcie,
nieczytelne dla LLM-a bez dodatkowego kontekstu.

Projekt `taxi-chat-data` ma w Fazie 3 zbudować czat, który tłumaczy pytania w
języku naturalnym na SQL (NL2SQL) i/lub odpowiada z wykorzystaniem RAG. Gdy
użytkownik pyta "ile przejazdów zapłacono gotówką?", model musi wiedzieć, że
"gotówka" odpowiada `payment_type = 2` — a nie zgadywać albo (gorzej)
halucynować mapowanie. Mając w hurtowni tabelę `payment_type_lookup` z
kolumną `payment_desc = 'Cash'`, można:

1. Dołączyć (`JOIN`) opis do faktów w warstwie `marts`, żeby wymiary miały już
   czytelne etykiety (`dim_payment_type.payment_desc`), więc zapytanie
   końcowe w ogóle nie musi znać surowych kodów.
2. Skarmić opisy słowników jako dokumentację/metadane do warstwy RAG w Fazie
   3 — LLM dostaje w kontekście "payment_type: 1=Credit card, 2=Cash, ...", co
   pozwala mu poprawnie zbudować `WHERE payment_type = 2` z pytania o
   "gotówkę", bez halucynacji.

To jest też kwestia **governance** (ładu danych): scentralizowane, przetestowane
(`not_null` + `unique` na kluczu) słowniki eliminują ryzyko, że dwa różne
modele albo dwie różne osoby zdefiniują "Cash" jako inny kod, albo że commit z
literówką w CSV przejdzie niezauważony — testy dbt failują pipeline zanim
błędne dane trafią do produktu.

## Pojęcie: conformed dimensions i reference/lookup data

W modelowaniu wymiarowym (Kimball) **conformed dimension** to wymiar o tej
samej definicji i kluczu, współdzielony przez wiele tabel faktów/procesów
biznesowych — dzięki temu różne raporty można łączyć i porównywać bez
niespójności ("ta sama strefa znaczy to samo wszędzie"). Nasze trzy seedy to
klasyczne **reference/lookup data**: małe tabele kod→etykieta, które w
kolejnym tasku (Task 5) staną się bazą dla wymiarów gwiazdy
(`dim_location`, `dim_payment_type`, `dim_ratecode`) przez `ref()` w modelach
dbt. Testy `unique`+`not_null` na kluczu gwarantują, że `JOIN` z tabelą faktów
nie namnoży wierszy (brak duplikatów klucza) i nie zgubi ich przez `NULL`
(brak dopasowania) — podstawowa higiena przy budowaniu gwiazdy.
