# Faza 2 / Task 7: End-to-end weryfikacja hurtowni (pełny `dbt build` + sanity join) — notatka do nauki

## Co robi pełny `dbt build` i dlaczego to jest "prawdziwy" dowód, że hurtownia działa

Do tej pory każdy task budował i testował **pojedynczy model** (`--select
stg_trips`, `--select fct_trips`, ...) w izolacji. `dbt build` bez `--select`
to co innego: buduje **cały DAG naraz**, w kolejności wynikającej z zależności
(`ref()`), i po każdym materializowanym węźle od razu odpala testy danych,
które go dotyczą, zanim przejdzie dalej. W tym projekcie DAG wygląda tak:

```
seeds (taxi_zone_lookup, payment_type_lookup, ratecode_lookup)
        │
        ▼
staging.stg_trips (view, czyta raw.trips)
        │
        ├──► marts.dim_location  ──┐
        ├──► marts.dim_payment   ──┤
        ├──► marts.dim_ratecode  ──┤
        └──► marts.dim_datetime  ──┤
                                    ▼
                          marts.fct_trips
```

dbt sam wylicza tę topologię z `ref()` w kodzie modeli — nie trzeba jej nigdzie
ręcznie deklarować. Testy (`not_null`, `unique`, `relationships`) są
**bramkami (gates)** wpiętymi w ten sam przebieg: jeśli test na `stg_trips`
albo na którymś seedzie zawiedzie, dbt i tak spróbuje zbudować dalsze węzły
(chyba że są od niego bezpośrednio zależne), ale commit i README nie powinny
iść dalej, dopóki *całość* nie kończy się `Completed successfully` z zerem
błędów. Innymi słowy: pojedynczy zielony model nic nie mówi o spójności
całego systemu — dopiero jeden, pełny `dbt build` od zera (surowe dane →
seedy → staging → wymiary → fakt → wszystkie testy) jest wiarygodnym dowodem,
że hurtownia jako całość jest poprawna.

Wynik tego uruchomienia w tym tasku:

```
Finished running 3 seeds, 5 table models, 25 data tests, 1 view model
in 0 hours 0 minutes and 30.02 seconds (30.02s).
Completed successfully
Done. PASS=34 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=34
```

34/34 węzłów (seedy + modele + testy) przeszło za jednym razem — to jest
właściwy "definition of done" dla Fazy 2.

## Jak model gwiazdy odpowiada na pytanie biznesowe przez JOIN-y

Tabela faktów (`fct_trips`) sama w sobie ma tylko **klucze obce** (liczby):
`pickup_location_id = 138`, `payment_type = 1`. Te liczby nic nie znaczą dla
człowieka ani dla LLM-a, dopóki nie połączy się ich z wymiarami, które niosą
opis:

```sql
SELECT l.borough, p.payment_desc, COUNT(*) AS trips, ROUND(SUM(f.total_amount),2) AS revenue
FROM marts.fct_trips f
JOIN marts.dim_location l ON f.pickup_location_id = l.location_id
JOIN marts.dim_payment  p ON f.payment_type      = p.payment_type
WHERE f.pickup_date = '2023-01-15'
GROUP BY 1, 2 ORDER BY revenue DESC
```

To jest dokładnie pytanie, jakie zadałby analityk albo docelowo warstwa NL2SQL
z Fazy 3: "przychód wg dzielnicy i metody płatności dla jednego dnia". Wynik
(fragment):

| borough   | payment_desc | trips | revenue      |
|-----------|--------------|-------|--------------|
| Manhattan | Credit card  | 67094 | 1 531 192.10 |
| Queens    | Credit card  |  7025 |   532 279.41 |
| Manhattan | Cash         | 13618 |   259 950.39 |

Kluczowy dowód: `borough` i `payment_desc` to **prawdziwe, czytelne nazwy**
(Manhattan, Queens, Credit card, Cash), a nie NULL-e ani surowe kody. Gdyby
klucze obce w fakcie nie pokrywały się z kluczami głównymi wymiarów (literówka
w `ref()`, zły typ kolumny, brak wiersza w seedzie), JOIN zwróciłby puste
wiersze albo w ogóle nic — a to właśnie testy `relationships` z Tasku 5
(sprawdzone ponownie w tym pełnym buildzie) gwarantują z wyprzedzeniem, żeby
taka sytuacja nigdy nie trafiła do produkcji niezauważona.

## Kluczowe pojęcia

- **DAG / lineage** — graf zależności między modelami wyprowadzony
  automatycznie z `ref()`; `dbt build` (bez `--select`) buduje i testuje cały
  graf w poprawnej kolejności topologicznej za jedno uruchomienie.
- **Testy jako bramki jakości (quality gates) w czasie budowy** — w
  przeciwieństwie do testów odpalanych "po fakcie" na już załadowanych
  danych, `dbt build` testuje **każdy węzeł od razu po jego materializacji**,
  więc regresja jest widoczna w tym samym przebiegu, w którym powstała.
- **Wymiar jako "słownik" dla kluczy obcych faktu** — sam klucz obcy (liczba)
  nie niesie znaczenia; dopiero JOIN do wymiaru tłumaczy go na coś, co
  człowiek albo LLM potrafi zinterpretować i po czym potrafi filtrować/
  grupować w naturalnym pytaniu.
- **Hurtownia jako queryable product** — po tym tasku `marts.*` jest gotowym,
  przetestowanym produktem: stabilny schemat, udokumentowane kolumny
  (governance z Tasków 2–5), gotowy pod warstwę GenAI (RAG + NL2SQL) w
  Fazie 3 — to ona będzie generować takie same zapytania SQL na podstawie
  pytań w języku naturalnym.

## Wynik (dowód działania)

`docker compose run --rm dbt build` (pełny, czysty build całego projektu) →
`Completed successfully`, `Done. PASS=34 WARN=0 ERROR=0 SKIP=0 NO-OP=0
TOTAL=34` — 3 seedy, 5 modeli tabelowych, 1 model widokowy, 25 testów
danych, wszystko zielone za jednym przebiegiem.

Sanity query (`bq query`) na `fct_trips JOIN dim_location JOIN dim_payment`
dla `pickup_date = '2023-01-15'` zwróciła realne wiersze z prawdziwymi
nazwami dzielnic i metod płatności (Manhattan/Credit card: 67 094 przejazdów,
1 531 192.10 przychodu; Queens/Credit card: 7 025 przejazdów, 532 279.41
przychodu) — model gwiazdy rozwiązuje się poprawnie end-to-end.

## Nota governance: dlaczego nie ma testów `accepted_values`

Projektowy spec (§7) wymieniał `accepted_values` na `payment_type` /
`ratecode_id` jako jeden z testów governance. Świadomie ich NIE dodaliśmy,
bo w tej hurtowni ich rolę pełnią mocniejsze testy `relationships`:

- `payment_type` — test `relationships` z `fct_trips` do `dim_payment`
  gwarantuje, że każda wartość kodu płatności istnieje w słowniku wymiaru
  (dziś kody 0–6). To ściślejsze niż statyczna lista `accepted_values`,
  bo dziedzina jest utrzymywana w jednym miejscu (seed → wymiar), a nie
  zduplikowana w YAML-u testu. Osobny `accepted_values` byłby redundantny.
- `ratecode_id` — świadomie NIE testujemy referencyjnie (patrz
  `faza-2-fact.md`): surowe dane niosą kody spoza słownika (np. RatecodeID
  99 = Null/unknown w oficjalnym słowniku TLC), które celowo zachowujemy.
  `accepted_values` ograniczony do 1–6 wywaliłby build na legalnie
  „brudnych" danych — dlatego byłby sprzeczny z decyzją projektową.

Wniosek: pokrycie governance jest zachowane (25 testów danych zielonych),
a odejście od litery specu jest świadome i udokumentowane tutaj.
