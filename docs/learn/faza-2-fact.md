# Faza 2 / Task 5: Tabela faktów `fct_trips` (partycjonowanie + klastrowanie) — notatka do nauki

## Czym jest tabela faktów

W modelu gwiazdy (star schema) **fakt** (fact) to zdarzenie/pomiar biznesowy
zapisane na ustalonym poziomie ziarnistości (grain) — tu: **jeden wiersz =
jeden przejazd taksówką**. Kolumny faktu dzielą się na dwie role:

- **klucze obce (foreign keys) do wymiarów** — `pickup_date` →
  `dim_datetime.date_key`, `pickup_location_id` / `dropoff_location_id` →
  `dim_location.location_id`, `payment_type` → `dim_payment.payment_type`,
  `ratecode_id` → `dim_ratecode.ratecode_id`. Te kolumny same w sobie nie
  niosą opisu — dają go dopiero JOIN-y do wymiarów.
- **miary (measures)** — liczby, które się agreguje: `fare_amount`,
  `tip_amount`, `tolls_amount`, `total_amount`, `trip_distance`,
  `trip_duration_min`, `passenger_count`. To one są przedmiotem `SUM`/`AVG`/
  `COUNT` w analitycznych zapytaniach.

`trip_key` to surogatowy klucz główny (surrogate key) wygenerowany już w
`stg_trips` (Task 3) z hashu kolumn źródłowych — testy `not_null` + `unique`
na nim gwarantują, że fakt ma dokładnie jeden wiersz na przejazd (grain jest
rzeczywiście zachowany, nie ma duplikacji przez np. wielokrotne ładowanie
tego samego pliku).

## Dlaczego partycjonowanie po `pickup_date`

BigQuery fizycznie dzieli tabelę partycjonowaną na osobne "kawałki" (jeden na
wartość klucza partycji — tu: jeden dzień). Analityczne zapytania o
przejazdy prawie zawsze filtrują po czasie ("przejazdy z stycznia 2023",
"ostatni tydzień") — silnik zapytań widzi filtr na `pickup_date` w `WHERE` i
**czyta z dysku wyłącznie partycje, które mogą zawierać pasujące wiersze**
(partition pruning), pomijając resztę tabeli całkowicie. Przy 3 mln wierszy
i danych rozłożonych na wiele dni to różnica między skanem całej tabeli a
skanem promila jej rozmiaru — mniej danych przeskanowanych = szybsze
zapytanie i niższy koszt (BigQuery liczy opłaty od ilości przeskanowanych
bajtów).

`pickup_date` (typ DATE, a nie pełny `TIMESTAMP`) jest tu też kluczem
łączącym z `dim_datetime.date_key` — ta sama kolumna pełni więc podwójną
rolę: klucz obcy do wymiaru czasu *i* klucz partycji fizycznego
przechowywania.

## Dlaczego klastrowanie po `pickup_location_id`

Klastrowanie (clustering) to drugi, "miękki" poziom fizycznej organizacji
danych — *wewnątrz* każdej partycji BigQuery sortuje/grupuje wiersze wg
podanej kolumny (tu: strefa odbioru pasażera). Typowe pytania w tym projekcie
("ile przejazdów wyjechało z Manhattanu w danym dniu", "suma napiwków wg
strefy") filtrują albo grupują po lokalizacji — klastrowanie sprawia, że
wiersze z tej samej strefy leżą blisko siebie fizycznie, więc silnik
zapytań musi doczytać mniej bloków danych, żeby znaleźć komplet pasujących
wierszy. W przeciwieństwie do partycji, klastrów może być praktycznie
dowolnie dużo (tu: 265 stref) — partycjonowanie po lokalizacji byłoby
nieopłacalne (za dużo małych partycji), stąd podział ról: partycja = czas
(gruboziarniste, częste filtrowanie zakresowe), klaster = lokalizacja
(drobnoziarniste, wysoka kardynalność).

## Dlaczego NIE ma testu `relationships` na `ratecode_id` i `dropoff_location_id`

To świadoma decyzja governance, a nie przeoczenie. Surowe dane NYC TLC
zawierają wartości spoza oficjalnych słowników — np. `RatecodeID = 99`
("Missing/Unknown" w praktyce, nieudokumentowane wprost w oficjalnym
schemacie 1–6) czy `DOLocationID` spoza zakresu 1–265 (rekordy z brakującą
lub błędną lokalizacją docelową w źródle). Świadomie **zachowujemy** te
"brudne" wiersze zamiast je odrzucać w `stg_trips` — bo:

1. To realne dane produkcyjne systemu źródłowego, nie błąd naszego
   pipeline'u — usuwanie ich fałszowałoby sumy/liczby przejazdów.
2. Test `relationships` na tych kolumnach failowałby **z definicji**, za
   każdym uruchomieniem `dbt build` — co uczyniłoby czerwony build "nowym
   normalnym" i maskowałoby prawdziwe regresje (syndrom "the boy who cried
   wolf": jeśli test zawsze jest czerwony, nikt nie zwraca uwagi, gdy
   pojawi się nowy, realny problem).

Dlatego testami `relationships` obejmujemy tylko kolumny, o których wiemy
(i zweryfikowaliśmy budując fakt), że są w pełni pokryte przez wymiar:
`pickup_date` (zakres dat faktu = dokładnie zakres `dim_datetime`),
`pickup_location_id` (1–265, pełne pokrycie przez `dim_location`) i
`payment_type`.

## Nieoczekiwane odkrycie przy budowie: `payment_type = 0`

Pierwsze uruchomienie `dbt build --select fct_trips` **faktycznie
zafailowało** test `relationships` na `payment_type` — 64 203 wiersze miały
`payment_type = 0`, kod nieobecny w oficjalnym słowniku TLC (1=Credit card
… 6=Voided trip). Sprawdzenie samego źródła (`raw.trips`) potwierdziło, że
kod 0 istnieje już w surowych danych (71 743 wiersze przed czyszczeniem w
`stg_trips`) — to nie błąd naszego kodu, tylko kolejna out-of-dictionary
wartość, tej samej natury co `RatecodeID = 99`.

Tu jednak decyzja poszła w drugą stronę niż dla `ratecode_id`/
`dropoff_location_id`: `payment_type` ma tylko 7 możliwych wartości (0–6),
więc rozszerzyliśmy słownik (`payment_type_lookup.csv`) o wiersz
`0,Flex fare trip` zamiast rezygnować z testu `relationships` na tej
kolumnie. To pokazuje ogólną zasadę: gdy kolumna ma **małą, znaną
kardynalność** i brakujący kod da się sensownie nazwać, lepiej uzupełnić
słownik (test zostaje silny i coś nas ochroni w przyszłości); gdy kolumna ma
**dużą kardynalność i realnie "śmieciowe" wartości** (przypadkowe kody spoza
zakresu, literówki źródła), lepiej świadomo zrezygnować z testu niż
sztucznie "wybielać" dane fałszywym wpisem w słowniku.

## Kluczowe pojęcia

- **Fact table vs. dimension table** — fakt: zdarzenia + miary + klucze obce,
  dużo wierszy; wymiar: opisowy kontekst, mało wierszy.
- **Grain** — poziom szczegółowości jednego wiersza faktu; tu: jeden
  przejazd. Musi być spójny w całej tabeli (żadna kolumna nie może
  "namnażać" wierszy ponad ten poziom).
- **Partition pruning** — silnik zapytań pomija całe partycje danych, które
  filtr `WHERE` wyklucza, zamiast skanować całą tabelę.
- **Clustering** — sortowanie/grupowanie danych wewnątrz partycji wg
  wskazanej kolumny (lub kolumn), przyspieszające filtrowanie/agregację po
  tej kolumnie bez tworzenia osobnych partycji.
- **Governance trade-off przy testach `relationships`** — test wymuszający
  integralność referencyjną jest cenny tylko wtedy, gdy odzwierciedla
  rzeczywiste, zamierzone ograniczenie danych; nakładanie go na kolumny ze
  znaną, akceptowaną "brudną" wartością zamienia sygnał w szum.

## Wynik (dowód działania)

`docker compose run --rm dbt build --select fct_trips` → tabela `fct_trips`
zbudowana (3,0 mln wierszy, partycjonowana + klastrowana), 6/6 testów danych
PASS (`not_null`+`unique` na `trip_key`, `not_null`+`relationships` na
`pickup_date`, `relationships` na `pickup_location_id` i `payment_type`) —
po uzupełnieniu `payment_type_lookup.csv` o kod `0`.

DDL potwierdzony przez `INFORMATION_SCHEMA.TABLES`:
```
PARTITION BY pickup_date
CLUSTER BY pickup_location_id;
```

`SELECT COUNT(*) FROM marts.fct_trips` = **2 998 748** — dokładnie tyle, ile
`stg_trips` (grain zachowany, brak namnożenia/utraty wierszy przy budowie
faktu).
