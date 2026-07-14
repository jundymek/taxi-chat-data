# Faza 2: wymiary star schema (`dim_location`, `dim_payment`, `dim_ratecode`, `dim_datetime`)

## Czym są wymiary w modelu gwiazdy (star schema)

Star schema (schemat gwiazdy) to klasyczny wzorzec modelowania hurtowni
danych: w centrum jest **tabela faktów** (fact table) — tu będzie to
`fct_trips` z Zadania 5 — zawierająca zdarzenia/pomiary (jeden przejazd =
jeden wiersz, z miarami jak `fare_amount`, `trip_distance`). Wokół niej,
połączone kluczami obcymi (foreign keys), stoją **tabele wymiarów**
(dimension tables) — to opisowy kontekst, po którym można te zdarzenia
grupować, filtrować i "kroić" (slice/dice): *kiedy* to się stało
(`dim_datetime`), *gdzie* (`dim_location`), *jak zapłacono*
(`dim_payment`), *jaką stawką* (`dim_ratecode`).

Sam kształt zapytań analitycznych ("suma przychodu wg dnia tygodnia i
dzielnicy") jest właśnie tym, do czego ten podział służy: fakty się
agreguje, wymiary się grupuje. Stąd nazwa "gwiazda" — fakt w środku, promienie
wymiarów dookoła.

## Dlaczego `dim_datetime` jest na poziomie ziarnistości DZIEŃ (day grain)

`dim_datetime` powstaje z `SELECT DISTINCT pickup_date FROM stg_trips` —
czyli ma dokładnie tyle wierszy, ile jest **unikalnych dat** w danych
źródłowych (u nas: 34 dni, od 2022-10-25 do 2023-02-01), a nie tyle, ile
jest przejazdów czy sekund w tym zakresie.

Ziarnistość (grain) wymiaru czasu musi pasować do ziarnistości, w jakiej
fakt będzie się z nim łączyć. `fct_trips` będzie partycjonowany po
`pickup_date` (kolumna typu DATE, wyliczona już w `stg_trips`), więc
`dim_datetime.date_key` też jest typu DATE — join `fct_trips.pickup_date =
dim_datetime.date_key` jest wtedy prosty i tani (join po dacie, nie po
pełnym timestampie).

Gdybyśmy wygenerowali wymiar czasu na poziomie godziny albo sekundy
(np. `SELECT DISTINCT pickup_datetime`), tabela wymiaru "eksplodowałaby"
do milionów wierszy (praktycznie tyle, ile ma sam fakt) — traci się wtedy
sens wymiaru jako małej, tanie-joinowalnej tabeli opisowej, i degeneruje
się on z powrotem w kopię faktu. Stąd świadomy wybór: dzień, nie sekunda.

## Dlaczego `dim_location`, `dim_payment`, `dim_ratecode` pochodzą z seedów

Te trzy wymiary nie są liczone z `stg_trips`, tylko wprost z seedów
(`taxi_zone_lookup`, `payment_type_lookup`, `ratecode_lookup`) załadowanych
w Zadaniu 2. Powody:

- **Conformed dimension** (wymiar współdzielony/spójny) — te same kody
  (np. `location_id`, `payment_type`) pojawiają się (i będą się pojawiać w
  przyszłości, Faza 4 streaming) w wielu źródłach/faktach. Trzymając ich
  definicję w jednym miejscu (seed → wymiar), każda tabela faktów, która
  kiedykolwiek powstanie, odwołuje się do tego samego słownika — nie
  duplikujemy logiki tłumaczenia kodu na opis w każdym fakcie z osobna.
- **Kompletność referencyjna niezależna od danych transakcyjnych** — np.
  `taxi_zone_lookup` ma 265 stref, nawet jeśli w danym batchu przejazdów
  pojawiła się tylko część z nich. Budowanie wymiaru z `stg_trips` (np.
  `SELECT DISTINCT PULocationID`) dawałoby niekompletny wymiar i psułoby
  test `relationships` we `fct_trips`, gdyby pojawił się kod spoza tego,
  co akurat widać w danych.
- **Dane słownikowe pochodzą z oficjalnej dokumentacji TLC** (NYC Taxi &
  Limousine Commission), a nie z samych danych transakcyjnych — to
  naturalnie "master data", a nie coś do wyprowadzania z faktów.

## Kluczowe pojęcia

- **Star schema (schemat gwiazdy)** — fakt w centrum + wymiary dookoła,
  połączone kluczami obcymi; optymalizowany pod odczyt/agregację (OLAP), w
  przeciwieństwie do znormalizowanego modelu OLTP.
- **Dimension vs. fact** — wymiar opisuje "kto/co/gdzie/kiedy" (kontekst,
  zwykle mało wierszy, dużo tekstowych atrybutów), fakt to zdarzenie/pomiar
  (dużo wierszy, liczby do agregacji + klucze obce do wymiarów).
- **Conformed dimension** — wymiar o tej samej definicji i kluczu,
  współdzielony przez wiele tabel faktów/źródeł, gwarantujący spójną
  interpretację tych samych kodów w całej hurtowni.
- **Degenerate key vs. surrogate key** — surrogate key (jak `trip_key` w
  `stg_trips`) to sztuczny klucz generowany przez warstwę ETL/ELT, nie
  pochodzący z systemu źródłowego. Degenerate dimension to sytuacja, gdy
  atrybut wymiarowy (np. numer zamówienia) zostaje w tabeli faktów bez
  osobnej tabeli wymiaru, bo nie ma żadnych dodatkowych atrybutów do
  opisania. Tu wszystkie klucze wymiarów (`location_id`, `payment_type`,
  `ratecode_id`, `date_key`) to naturalne klucze (natural keys) z systemu
  źródłowego/seedów — nie generujemy dla nich osobnych surrogate keys, bo
  są już unikalne i stabilne.

## Wynik (dowód działania)

`docker compose run --rm dbt build --select dim_location dim_payment
dim_ratecode dim_datetime` — 4 tabele zbudowane w `marts`, 8 testów danych
(`not_null` + `unique` na kluczu każdego wymiaru) PASS.

Liczby wierszy: `dim_location` = **265**, `dim_payment` = **6**,
`dim_ratecode` = **6**, `dim_datetime` = **34** (dokładnie tyle, ile
unikalnych dat przejazdów w `stg_trips`, zakres 2022-10-25 — 2023-02-01) —
potwierdza, że wymiar czasu nie "eksplodował" do ziarnistości godzinowej
czy sekundowej.
