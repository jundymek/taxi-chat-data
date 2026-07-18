# Faza 6 – scalenie streamu z batchem w `stg_trips`

Notatka do nauki: jak połączyć dane wsadowe (`raw.trips`) ze strumieniowymi
(`stream.trips` z Fazy 4) w jednym modelu staging, tak żeby ten sam przejazd,
który przyszedł obiema drogami, liczył się dokładnie raz.

## Dlaczego scalamy w warstwie staging, a nie w marcie

`stg_trips` to jedno, kanoniczne źródło „oczyszczonych przejazdów”. Wszystko nad
nim (`fct_trips`, wymiary, potem eval i pytania NL2SQL) buduje się z tego modelu.
Gdybyśmy scalali stream dopiero w marcie, każdy mart musiałby powtarzać tę samą
logikę deduplikacji i te same filtry jakości. Scalając raz, w staging:

- filtry jakości (ujemne kwoty, zerowy dystans, niemożliwe daty) stosujemy w
  jednym miejscu dla obu źródeł,
- deduplikacja przejazdu batch↔stream dzieje się raz,
- warstwy wyżej nie wiedzą (i nie muszą wiedzieć), że dane mają dwa źródła.

To jest sens warstwy staging: „ujednolić i wyczyścić u wejścia”.

## Deterministyczny klucz: `generate_surrogate_key`

`dbt_utils.generate_surrogate_key([...])` liczy hash (MD5) z konkatenacji
podanych kolumn rzutowanych na tekst. Kluczowa cecha: jest **deterministyczny** —
te same wartości wejściowe zawsze dają ten sam hash. Dzięki temu klucz może
służyć jako identyfikator przejazdu bez sekwencji/autoinkrementu.

W `stg_trips` klucz liczymy z 6 pól:
`pickup_datetime, dropoff_datetime, pickup_location_id, dropoff_location_id,
fare_amount, vendor_id` (dla `raw` – ich surowe nazwy TLC: `tpep_pickup_datetime`
itd.). Ta sama szóstka, w tej samej kolejności, po obu stronach.

## Dlaczego PRZELICZAMY klucz po stronie stream, zamiast ufać zapisanemu

`stream.trips` ma już kolumnę `trip_key` – konsument z Fazy 4
(`ingestion/stream_common.py`) policzył ją tą samą recepturą (te same 6 pól, ta
sama kolejność, ten sam sentinel dla NULL-a) i użył jako `insertId` w BigQuery.
Moglibyśmy więc jej zaufać. Nie robimy tego świadomie:

- **Jedno źródło prawdy.** Klucz definiuje makro w dbt. Gdyby konsument w
  przyszłości zmienił formułę (dodał pole, zmienił kolejność), zapisany klucz
  „rozjechałby się” z batchowym i dedup przestałby działać po cichu.
- Przeliczając klucz w `stream_cleaned` tym samym makrem co w `raw_cleaned`,
  gwarantujemy, że przejazd obecny w obu źródłach dostaje **identyczny** klucz —
  niezależnie od tego, co zrobił producent/konsument.

To wzorzec „nie ufaj wartości spoza swojej warstwy, przelicz ją u siebie”.

## `union all` + dedup zamiast `union distinct`

Model składa dwa CTE:

```sql
unioned as (
    select * from raw_cleaned
    union all
    select * from stream_cleaned
),
deduped as (
    select *
    from unioned
    qualify row_number() over (
        partition by trip_key order by pickup_datetime
    ) = 1
)
```

Dlaczego `union all`, a nie `union distinct`?

- `union distinct` deduplikowałby po **całym wierszu** – dwa wpisy tego samego
  przejazdu musiałyby być identyczne we wszystkich kolumnach, żeby się skleiły.
  Batch i stream mogą się różnić drobiazgami (typy, zaokrąglenia), więc
  `union distinct` mógłby przepuścić duplikat.
- My chcemy deduplikować po **kluczu biznesowym** (`trip_key`), nie po całym
  wierszu. Dlatego `union all` (tanie, bez sortowania) + jawna deduplikacja po
  kluczu.

## `qualify row_number()` – deduplikacja przejazdu z obu dróg

`row_number() over (partition by trip_key order by pickup_datetime)` numeruje
wiersze w obrębie każdego `trip_key`. `qualify ... = 1` zostawia dokładnie jeden
wiersz na klucz. `order by pickup_datetime` daje **deterministyczny** tie-break –
przy tym samym kluczu zawsze wybierzemy ten sam wiersz, więc wynik buildu jest
powtarzalny. `qualify` to skrót BigQuery: filtruje po funkcji okna bez
opakowywania w podzapytanie.

## Co udowodniła weryfikacja

Przed scaleniem: `stg_trips` (tylko raw) = 2 998 748 wierszy, wszystkie unikalne.
`stream.trips` = 99 998 wierszy. Po scaleniu:

```
n = 2 998 748,  uniq = 2 998 748
```

- `n == uniq` → pełna deduplikacja (test `unique` na `trip_key` też przechodzi).
- `n` nie wzrosło mimo dorzucenia 99 998 wierszy streamu → **wszystkie** wiersze
  streamu (który jest odtworzeniem tego samego parquet, co batch) rozpoznały się
  jako duplikaty swoich batchowych bliźniaków. Przeliczony klucz trafił co do
  jednego. To najlepszy dowód, że receptura klucza jest spójna po obu stronach.

Gdyby stream niósł przejazdy nieobecne w batchu, `n` wzrosłoby o ich liczbę – i
to też byłoby poprawne (warunek akceptacji to `n ≥ liczba sprzed Fazy 6`).
