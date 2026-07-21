# Ścieżka jednego rekordu — przewodnik po plikach

Notatka do nauki (PL). Ten dokument śledzi **jeden przejazd taksówką** od pliku
Parquet na serwerze Nowego Jorku aż do zdania, które widzisz w czacie. Krok po
kroku, plik po pliku.

**Czym różni się od [00-caly-system.md](00-caly-system.md):** tamten tłumaczy
**dlaczego** — czym jest Parquet, po co Pub/Sub, skąd się biorą duplikaty. Ten
odpowiada na **gdzie i w jakiej kolejności** — który plik, która funkcja, co
wchodzi, co wychodzi. Czytaj oba: tamten żeby zrozumieć, ten żeby się połapać.

**Do czego służy:** żebyś mógł usiąść z rekruterem, otwierać kolejne pliki i
opowiadać, co się w nich dzieje — bez zgadywania, co było wcześniej.

**Jak czytać:** otwórz projekt obok i faktycznie klikaj w linki. Numery linii
są kotwicami — mogą się przesunąć po zmianach w kodzie, więc gdy coś nie
pasuje, szukaj po nazwie funkcji.

---

## Mapa w jednym akapicie

Przejazd wchodzi do systemu **dwiema drogami naraz** (wsadową i strumieniową),
obie lądują w BigQuery, dbt je **czyści i scala w jeden wiersz**, buduje z nich
gwiazdę (fakt + wymiary), a potem osobna warstwa GenAI zamienia Twoje pytanie na
SQL, sprawdza go pod kątem bezpieczeństwa, wykonuje i streszcza wynik po ludzku.

```
[1] download → [2a] batch  ─┐
                            ├→ [3] stg_trips → [4] gwiazda → [7-11] GenAI → [12] frontend
               [2b] stream ─┘
```

---

## Krok 1 — Skąd się bierze plik

**Plik:** [ingestion/download.py](../../ingestion/download.py) · funkcja `download_taxi_parquet`
**Wchodzi:** miesiąc w formacie `YYYY-MM` (z `.env`, domyślnie `2023-01`)
**Wychodzi:** `data/yellow_tripdata_2023-01.parquet` (~3 mln wierszy)

Miasto Nowy Jork publikuje pliki Parquet pod stałym adresem
([`BASE_URL`, linia 8](../../ingestion/download.py#L8)). Funkcja składa URL,
pobiera plik strumieniowo (kawałkami po 1 MB, żeby nie wciągać całości do RAM)
i zapisuje na dysk.

**Na co zwrócić uwagę — dwie rzeczy, o które łatwo się potknąć:**

1. **Walidacja miesiąca** ([`_MONTH_RE`, linia 12](../../ingestion/download.py#L12)).
   Wartość z `.env` trafia zarówno do URL-a, jak i do ścieżki na dysku. Bez
   sprawdzenia formatu ktoś mógłby wpisać `../../etc/passwd` i wyjść poza katalog
   danych. To jest ochrona przed *path traversal*.
2. **Pobieranie do pliku `.part`** ([linie 38-51](../../ingestion/download.py#L38)).
   Gdyby pobieranie padło w połowie i został niekompletny plik pod docelową
   nazwą, następne uruchomienie zobaczyłoby „plik istnieje, pomijam" i pracowało
   na uciętych danych. Dlatego zapis idzie do `.part`, a `os.replace` (operacja
   atomowa) nadaje właściwą nazwę dopiero po sukcesie. Blok `except` sprząta
   ogryzek.

→ **Dalej:** ten sam plik czytają dwie niezależne drogi — krok 2a i 2b.

---

## Krok 2a — Droga wsadowa: plik → GCS → BigQuery

**Plik:** [ingestion/batch_load.py](../../ingestion/batch_load.py) · funkcja `run_batch` ([linia 68](../../ingestion/batch_load.py#L68))
**Wchodzi:** ścieżka do Parquetu
**Wychodzi:** tabela `raw.trips` w BigQuery + liczba wczytanych wierszy

`run_batch` to cztery kroki pod rząd — najlepsze miejsce, żeby zacząć czytanie
tego pliku:

| Kolejność | Funkcja | Co robi |
|---|---|---|
| 1 | `ensure_bucket` ([:14](../../ingestion/batch_load.py#L14)) | tworzy bucket GCS, jeśli nie istnieje |
| 2 | `upload_to_gcs` ([:29](../../ingestion/batch_load.py#L29)) | wrzuca plik pod `raw/<nazwa>` |
| 3 | `ensure_dataset` ([:42](../../ingestion/batch_load.py#L42)) | tworzy dataset `raw` w BigQuery |
| 4 | `load_gcs_to_bq` ([:51](../../ingestion/batch_load.py#L51)) | ładuje z GCS do tabeli `raw.trips` |

**Dlaczego przez GCS, a nie prosto z dysku do BigQuery?** Bo GCS pełni tu rolę
**data lake** — surowy plik zostaje w oryginalnej postaci. Jeśli za pół roku
zmienisz logikę czyszczenia, przeładujesz z GCS, nie pobierając ponownie z TLC.

**Na co zwrócić uwagę:**

- **Idempotentność.** Każdy krok można uruchomić dwa razy bez szkody:
  `exists_ok=True` przy datasecie, przechwycony `Conflict` przy buckecie
  ([linia 22](../../ingestion/batch_load.py#L22) — łapie wyścig między
  `lookup_bucket` a `create_bucket`), a `WRITE_TRUNCATE`
  ([linia 56](../../ingestion/batch_load.py#L56)) nadpisuje tabelę zamiast
  dopisywać duplikaty.
- **`load_job.output_rows`, nie `table.num_rows`** ([linie 61-63](../../ingestion/batch_load.py#L61)).
  Metadane tabeli potrafią się spóźnić tuż po załadowaniu; licznik zadania jest
  autorytatywny od razu.
- **`autodetect=True`** — schemat bierze się z samego Parquetu. Dlatego w `raw`
  siedzą oryginalne nazwy z TLC (`VendorID`, `tpep_pickup_datetime`), a nie nasze.

→ **Dalej:** krok 3 (dbt) — ale najpierw zobacz drugą drogę.

---

## Krok 2b — Droga strumieniowa: Parquet → Pub/Sub → BigQuery

Ta droga udaje, że dane płyną na żywo. Ma **trzy pliki** i to jest miejsce, w
którym najłatwiej się pogubić, bo producent i konsument to osobne procesy.

### 2b-1. Wspólny kontrakt

**Plik:** [ingestion/stream_common.py](../../ingestion/stream_common.py)

To jest najważniejszy plik tej drogi, choć nic sam nie uruchamia. Producent i
konsument muszą się zgadzać co do: zestawu pól
([`MESSAGE_FIELDS`, :20](../../ingestion/stream_common.py#L20)), przepisu na
klucz ([`SURROGATE_KEY_FIELDS`, :29](../../ingestion/stream_common.py#L29)),
kodowania JSON i nazw zasobów. Wszystko to leży **tutaj**, w jednym miejscu.

**Najciekawszy fragment w całym pliku —** [`_bq_string`, linie 61-70](../../ingestion/stream_common.py#L61).
Klucz `trip_key` musi wyjść **identyczny** jak ten, który dbt policzy w SQL-u.
A dbt hashuje tekst po `CAST(x AS STRING)` w BigQuery. Więc Python musi
renderować wartości dokładnie tak, jak robi to BigQuery: datę jako
`%Y-%m-%d %H:%M:%S+00`, float `1.0` jako `1`, `NULL` jako sentinel
`_dbt_utils_surrogate_key_null_` ([:35](../../ingestion/stream_common.py#L35)).
Jedna niezgodność i dedup w kroku 3 przestaje działać — a zobaczyłbyś to dopiero
jako zdublowane wiersze w hurtowni.

### 2b-2. Producent

**Plik:** [ingestion/stream_producer.py](../../ingestion/stream_producer.py) · funkcja `replay` ([:33](../../ingestion/stream_producer.py#L33))
**Wchodzi:** ten sam Parquet · **Wychodzi:** wiadomości w kolejce Pub/Sub

Czyta Parquet partiami po 1000 wierszy, każdy wiersz zamienia na JSON
(`row_to_message`) i publikuje. `--rate` dławi tempo do zadanej liczby wiadomości
na sekundę ([linie 51-56](../../ingestion/stream_producer.py#L51)), żeby wyglądało
jak żywy ruch.

**Na co zwrócić uwagę:** [`--dup-rate`, linie 48-50](../../ingestion/stream_producer.py#L48)
— producent **celowo publikuje część wiadomości dwa razy**. To nie jest błąd, to
symulacja gwarancji *at-least-once*: prawdziwe kolejki dostarczają duplikaty i
system musi sobie z tym radzić. Krok 3 to naprawia.

Drugi detal: `finally` z `future.result()` ([linie 59-63](../../ingestion/stream_producer.py#L59))
— nawet po Ctrl+C czekamy na potwierdzenie wiadomości już przekazanych klientowi,
żeby ich nie zgubić.

### 2b-3. Konsument

**Plik:** [ingestion/stream_consumer.py](../../ingestion/stream_consumer.py) · klasa `BatchWriter` ([:25](../../ingestion/stream_consumer.py#L25))
**Wchodzi:** wiadomości z Pub/Sub · **Wychodzi:** wiersze w `stream.trips`

Zbiera wiadomości do bufora i wstawia partiami po 500 (pojedyncze wstawki byłyby
wolne i drogie). Serce to
[`_flush_locked`, linie 68-89](../../ingestion/stream_consumer.py#L68).

**Na co zwrócić uwagę — na tym polega poprawność tej drogi:**

- **`ack` dopiero po udanym zapisie** ([:87-88](../../ingestion/stream_consumer.py#L87)).
  Potwierdzenie wiadomości mówi Pub/Subowi „możesz o niej zapomnieć". Gdybyśmy
  potwierdzali przed zapisem, awaria BigQuery = bezpowrotnie utracone dane.
- **Błąd → `nack` całej partii** ([:80-86](../../ingestion/stream_consumer.py#L80)).
  Pub/Sub dostarczy je ponownie. Część wierszy mogła już wylądować — i tu ratuje
  nas `row_ids=trip_key` ([:73-75](../../ingestion/stream_consumer.py#L73)):
  BigQuery sam odrzuca powtórzone `insertId`.
- **Uszkodzona wiadomość → log + `ack` + licznik** ([:53-57](../../ingestion/stream_consumer.py#L53)).
  Świadome uproszczenie: bez kolejki dead-letter w tej fazie. Gdybyśmy ją
  nackowali, wracałaby w kółko i zablokowała strumień.
- **Reset licznika bezczynności przy nacku** ([:112-115](../../ingestion/stream_consumer.py#L112)).
  Bez tego konsument mógłby się wyłączyć jako „bezczynny", czekając na ponowne
  dostarczenie partii, którą sam odrzucił.

→ **Dalej:** obie drogi spotykają się w kroku 3.

---

## Krok 3 — Czyszczenie i scalenie obu dróg ⭐

**Plik:** [dbt/models/staging/stg_trips.sql](../../dbt/models/staging/stg_trips.sql)
**Wchodzi:** `raw.trips` (droga wsadowa) **oraz** `stream.trips` (strumieniowa)
**Wychodzi:** widok `staging.stg_trips` — jeden czysty wiersz na przejazd

To **najważniejszy plik w całym projekcie** i najlepszy do pokazania na
rozmowie. Czyta się go z góry na dół jak listę kroków (CTE po CTE):

| CTE | Linie | Co robi |
|---|---|---|
| `raw_source` / `raw_cleaned` | [3-41](../../dbt/models/staging/stg_trips.sql#L3) | zmiana nazw na `snake_case`, typy, filtry sensowności |
| `stream_source` / `stream_cleaned` | [43-83](../../dbt/models/staging/stg_trips.sql#L43) | to samo dla strumienia |
| `unioned` | [85-94](../../dbt/models/staging/stg_trips.sql#L85) | sklejenie obu z oznaczeniem źródła |
| `deduped` | [96-103](../../dbt/models/staging/stg_trips.sql#L96) | jeden wiersz na `trip_key` |

**Trzy rzeczy, które warto umieć wyjaśnić:**

**1. `trip_key` — klucz z treści, nie z licznika** ([linie 9-16](../../dbt/models/staging/stg_trips.sql#L9)).
`generate_surrogate_key` hashuje sześć pól (czas odbioru, czas dowozu, obie
lokalizacje, kwota, przewoźnik). Ten sam przejazd daje ten sam hash niezależnie
od tego, którą drogą przyszedł — i **tylko dlatego** dedup jest w ogóle możliwy.
Zwróć uwagę, że blok w `stream_cleaned` ([:51](../../dbt/models/staging/stg_trips.sql#L51))
wymienia te same sześć pól w tej samej kolejności, tylko pod innymi nazwami
kolumn. To jest ten sam kontrakt, co `SURROGATE_KEY_FIELDS` w Pythonie.

**2. Filtry** ([linie 35-41](../../dbt/models/staging/stg_trips.sql#L35)).
Odrzucamy ujemne kwoty, zerowe dystanse, dowóz przed odbiorem, daty sprzed 2009
i z przyszłości. Realne dane TLC zawierają wszystkie te przypadki.

**3. Dedup — i pułapka, którą trzeba było obejść** ([linie 86-103](../../dbt/models/staging/stg_trips.sql#L86)).
`qualify row_number() over (partition by trip_key order by ...)` zostawia jeden
wiersz z każdej grupy o tym samym kluczu. Ale **czym sortować**?

- `source_rank` (0 dla wsadu, 1 dla strumienia) sprawia, że wygrywa wsad —
  autorytatywne, kompletne źródło.
- `to_json_string(unioned)` to rozstrzygnięcie ostateczne, deterministyczne
  względem treści.

Komentarz w kodzie tłumaczy, dlaczego **`pickup_datetime` by nie wystarczył**:
jest częścią `trip_key`, więc każda para duplikatów remisuje na nim, a BigQuery
wybierałby zwycięzcę arbitralnie — i `stg_trips` zmieniałby się między buildami
bez zmiany danych. To jest dokładnie ten rodzaj szczegółu, który pokazuje, że
rozumiesz determinizm w SQL-u.

→ **Dalej:** krok 4 — gwiazda.

---

## Krok 4 — Gwiazda: fakt i wymiary

**Katalog:** [dbt/models/marts/](../../dbt/models/marts/)
**Wchodzi:** `staging.stg_trips` + seedy CSV · **Wychodzi:** dataset `marts`

Klasyczny model gwiazdy: jedna wielka tabela faktów w środku, małe tabele
wymiarów dookoła.

**Fakt** — [fct_trips.sql](../../dbt/models/marts/fct_trips.sql). Same przejazdy:
klucze obce i miary (kwoty, dystans, czas). Cała treść to `select ... from
{{ ref('stg_trips') }}` — ale najważniejsze są **pierwsze pięć linii**:

```sql
partition_by={'field': 'pickup_date', 'data_type': 'date'},
cluster_by=['pickup_location_id']
```

- **Partycjonowanie** po dacie: BigQuery trzyma każdy dzień osobno, więc pytanie
  o jeden dzień czyta 1/31 danych, nie całość. W BigQuery płacisz za
  przeskanowane bajty — to jest wprost pieniądze.
- **Klastrowanie** po miejscu odbioru: w obrębie partycji wiersze leżą
  posortowane, więc filtr po lokalizacji też czyta mniej.

**Wymiary** — cztery, każdy inaczej zbudowany, i to jest ciekawe:

| Plik | Skąd bierze dane |
|---|---|
| [dim_datetime.sql](../../dbt/models/marts/dim_datetime.sql) | **wyliczany** z `stg_trips` — `distinct pickup_date` + rozbicie na rok/miesiąc/dzień tygodnia/weekend |
| [dim_location.sql](../../dbt/models/marts/dim_location.sql) | **seed** `taxi_zone_lookup.csv` (265 stref NYC) |
| [dim_payment.sql](../../dbt/models/marts/dim_payment.sql) | seed — `1 → Credit card` itd. |
| [dim_ratecode.sql](../../dbt/models/marts/dim_ratecode.sql) | seed — taryfy |

Seedy leżą w [dbt/seeds/](../../dbt/seeds/) — to małe słowniki wersjonowane
razem z kodem, bo zmieniają się raz na lata.

**Do czego to służy:** bez `dim_payment` model LLM musiałby wiedzieć, że
`payment_type = 1` to karta. Z wymiarem po prostu robi `JOIN` i czyta `Credit
card`. Wymiary są **równie ważne dla LLM-a, co dla człowieka**.

**Plik, który trzeba znać:** [\_marts\_\_models.yml](../../dbt/models/marts/_marts__models.yml).
To nie jest dokumentacja dla ludzi — **to jest kontekst schematu podawany
modelowi** w kroku 6. Nieudokumentowana kolumna to kolumna, której nazwę model
musi zgadnąć. (Ta pułapka jest zapisana w [CLAUDE.md](../../CLAUDE.md).)

→ **Dalej:** krok 5 to dowód, że partycje działają; właściwa ścieżka pytania
zaczyna się w kroku 6.

---

## Krok 5 — Dowód, że partycjonowanie działa (obok ścieżki)

**Plik:** [analysis/measure_partitioning.py](../../analysis/measure_partitioning.py) · `dry_run_bytes` ([:33](../../analysis/measure_partitioning.py#L33))

Tworzy kopię `fct_trips` **bez** partycji i klastrów
([`build_unpartitioned_copy`, :23](../../analysis/measure_partitioning.py#L23)),
po czym odpala to samo zapytanie na obu wersjach w trybie **dry-run** — BigQuery
mówi, ile bajtów by przeczytał, nic nie wykonując ani nie płacąc.

Wynik to liczba do README: „partycjonowanie ogranicza skan o X%". Nie twierdzisz,
że optymalizacja działa — **mierzysz to**.

---

## Krok 6 — Schemat trafia do bazy wektorowej

**Plik:** [genai/indexer.py](../../genai/indexer.py) · `load_model_docs` ([:27](../../genai/indexer.py#L27))
**Wchodzi:** pliki YAML z `dbt/models/` · **Wychodzi:** katalog `data/chroma`

Tu zaczyna się warstwa GenAI. Indekser czyta **YAML-e dbt** (te same, które
dokumentują modele), zamienia każdy model na blok tekstu
(`format_model_doc`, [:19](../../genai/indexer.py#L19)) w rodzaju:

```
Table marts.fct_trips: Trip fact table.
Columns:
- trip_key: Deterministic surrogate key...
```

…zamienia ten tekst na wektor (model `nomic-embed-text`) i zapisuje w Chromie.
To samo robi z ręcznie napisanymi przykładami z
[genai/examples.yml](../../genai/examples.yml).

**Na co zwrócić uwagę:**

- **YAML dbt to jedyne źródło prawdy** — opisy schematu nie są nigdzie
  przepisywane ręcznie. Zmieniasz opis kolumny w dbt, przebudowujesz indeks,
  model widzi nowy opis.
- **Prefiks decyduje o datasecie** ([:20](../../genai/indexer.py#L20)): model
  zaczynający się od `stg_` → `staging`, każdy inny → `marts`.
- **Indeks trzeba przebudować ręcznie:** `python -m genai.indexer`. `data/chroma`
  to zmaterializowana kopia — edycja YAML-a sama jej nie odświeży (kolejna
  pułapka z [CLAUDE.md](../../CLAUDE.md)).
- **`raw` celowo NIE jest indeksowany** — model nie ma nawet wiedzieć, że
  istnieje surowy dataset.

→ **Dalej:** od tego miejsca zaczyna się obsługa pojedynczego pytania.

---

## Krok 7 — Pytanie → kontekst (RAG)

**Plik:** [genai/retriever.py](../../genai/retriever.py) · `Retriever.retrieve` ([:19](../../genai/retriever.py#L19))
**Wchodzi:** pytanie użytkownika · **Wychodzi:** `SchemaContext` (4 opisy tabel + 3 przykłady)

Pytanie zamieniane jest na wektor, a Chroma zwraca **najbliższe** mu opisy tabel
i przykłady. Do promptu trafia więc tylko to, co pasuje do pytania — nie cały
schemat.

**Dlaczego nie wkleić całego schematu?** Przy pięciu tabelach dałoby się. Ale
RAG jest tu po to, żeby pokazać wzorzec, który skaluje się do dwustu tabel,
gdzie cały schemat nie zmieściłby się w oknie kontekstu.

Detal: [`k = min(k, collection.count())`](../../genai/retriever.py#L28) — Chroma
przewraca się przy prośbie o więcej wyników, niż ma dokumentów. Broni to świeżo
zbudowanego, małego indeksu.

Kontrakt wyjścia: [`SchemaContext`](../../genai/types.py#L10).

---

## Krok 8 — Pytanie → SQL

**Plik:** [genai/nl2sql.py](../../genai/nl2sql.py) · `generate_sql` ([:48](../../genai/nl2sql.py#L48))
**Wchodzi:** pytanie + `SchemaContext` · **Wychodzi:** tekst SQL

Trzy proste funkcje: `build_prompt` skleja prompt, model generuje odpowiedź,
`extract_sql` wyciąga z niej kod.

- [`SYSTEM_PROMPT` (:6)](../../genai/nl2sql.py#L6) — instrukcja: dokładnie jeden
  `SELECT`, w bloku ```sql, tylko z podanych tabel, zawsze w pełni kwalifikowany.
- [`extract_sql` (:40)](../../genai/nl2sql.py#L40) — próbuje ```sql, potem
  dowolnego bloku ```, a na końcu bierze całą odpowiedź. Modele lokalne bywają
  niekonsekwentne w formatowaniu, więc to jest świadoma **kaskada awaryjna**.
- [`error_feedback` (:25)](../../genai/nl2sql.py#L25) — jeśli poprzednia próba
  została odrzucona, powód wchodzi do promptu. Tego używa pętla z kroku 10.

**Uwaga o niespójności w kodzie:** `SYSTEM_PROMPT` kończy się zdaniem *„The
user's question is in Polish"*, podczas gdy prompt streszczający
([pipeline.py:15-20](../../genai/pipeline.py#L15)) każe odpowiadać w języku
pytania, a UI jest po angielsku. To pozostałość po czasach, gdy aplikacja była
polska. Nie psuje działania (dotyczy generowania SQL-a, nie odpowiedzi), ale
jeśli rekruter to wypatrzy — to jest prawdziwy drobny dług, nie feature.

---

## Krok 9 — Bramka bezpieczeństwa ⭐

**Plik:** [genai/guardrails.py](../../genai/guardrails.py) · `validate` ([:25](../../genai/guardrails.py#L25))
**Wchodzi:** SQL od modelu · **Wychodzi:** [`ValidationResult`](../../genai/types.py#L17) (ok / powód odmowy)

Drugi plik wart pokazania na rozmowie. Pytanie, które zawsze pada: *„a co jeśli
model wygeneruje `DELETE`?"* — odpowiedź jest tutaj. **Pięć bramek po kolei**
(spis na górze pliku, linie 1-13):

| # | Bramka | Linie |
|---|---|---|
| 1 | Parsuje się? (sqlglot, dialekt BigQuery) | [28-32](../../genai/guardrails.py#L28) |
| 2 | Dokładnie **jedna** instrukcja | [34-36](../../genai/guardrails.py#L34) |
| 3 | To musi być `SELECT` (lub `UNION`) | [38-41](../../genai/guardrails.py#L38) |
| 4 | Każda tabela w dozwolonym datasecie | [43-68](../../genai/guardrails.py#L43) |
| 5 | Dry-run: ile bajtów by zeskanował | [74-97](../../genai/guardrails.py#L74) |

Plus wymuszenie `LIMIT` ([:70-72](../../genai/guardrails.py#L70)), gdy go brakuje.

**Bramka 2 nie jest zbędna:** `SELECT 1; DROP TABLE x` parsuje się jako dwie
instrukcje i pierwsza jest niewinna. Sprawdzenie „czy to SELECT" na samym
początku by tego nie złapało.

**Najciekawszy fragment —** [`build_scope`, linie 43-52](../../genai/guardrails.py#L43).
Naiwna implementacja sprawdzałaby nazwy tabel i pomijała te, które wyglądają na
CTE. Ale wtedy:

```sql
WITH trips AS (SELECT * FROM trips) SELECT * FROM trips
```

…przemyciłoby prawdziwą, niekwalifikowaną tabelę `trips` — bo nazwa zgadza się z
nazwą CTE. `build_scope` ze sqlglota rozwiązuje **każde** źródło do tego, czym
naprawdę jest: odwołanie do CTE do jego definicji, prawdziwa tabela zostaje
`exp.Table`. Dopiero to jest bezpieczne.

Dwa dodatkowe zabezpieczenia w bramce 4-5:

- **Wymóg pełnej kwalifikacji** ([:54-61](../../genai/guardrails.py#L54)): bez
  nazwy projektu BigQuery rozwiązałby tabelę względem domyślnego projektu klienta
  — czyli cicho, nie tam, gdzie myślisz.
- **Dry-run** ([:80-97](../../genai/guardrails.py#L80)): BigQuery wycenia
  zapytanie bez wykonywania. Powyżej 1 GB
  ([`MAX_SCAN_BYTES`](../../genai/config.py#L22)) — odmowa. To jest hamulec
  kosztowy: halucynacja modelu nie wygeneruje rachunku.

Lista dozwolonych datasetów: [`ALLOWED_DATASETS`](../../genai/config.py#L20) —
`staging` i `marts`. Nigdy `raw` ani `stream`.

---

## Krok 10 — Graf z pętlą ponawiania ⭐

**Plik:** [genai/pipeline.py](../../genai/pipeline.py) · `build_pipeline` ([:38](../../genai/pipeline.py#L38))
**Wchodzi:** pytanie · **Wychodzi:** stan z odpowiedzią (albo odmową)

Trzeci plik wart pokazania. Spina kroki 7-9 w graf (LangGraph), gdzie każdy
węzeł to funkcja, a stan przechodzi między nimi
([`AskState`, :25](../../genai/pipeline.py#L25)).

```
retrieve → generate_sql → validate ─(ok)→ execute → summarize → END
                              ↑ │
                (błąd, próba<3)│ └─(błąd, próba=3)→ refuse → END
                              │
                       generate_sql
```

**Dlaczego graf, a nie zwykłe `if`-y?** Odpowiedź to
[`route_after_validate`, linie 72-77](../../genai/pipeline.py#L72) — **krawędź
wsteczna** `validate → generate_sql`. Gdy guardrails odrzuci SQL, powód wraca do
modelu jako `error_feedback` i ten próbuje ponownie, do trzech razy
([`MAX_SQL_ATTEMPTS`](../../genai/config.py#L24)). Model uczy się z własnego
błędu w obrębie jednego pytania. Po trzeciej porażce → `refuse`, czyli uczciwa
odmowa zamiast zmyślonej odpowiedzi.

**Na co zwrócić uwagę:**

- **Wstrzykiwanie zależności** ([:38-53](../../genai/pipeline.py#L38)):
  `llm`, `retriever`, `validate_fn`, `bq_client` można podać z zewnątrz — dlatego
  testy w `tests/test_pipeline.py` działają bez Ollamy i BigQuery.
- **Ten sam klient BQ do dry-runu i wykonania**
  ([:51-53](../../genai/pipeline.py#L51)): inaczej walidacja i wykonanie mogłyby
  rozjechać się co do projektu, uprawnień albo lokalizacji.
- **Podwójny hamulec kosztowy** ([:83](../../genai/pipeline.py#L83)): oprócz
  dry-runu wykonanie dostaje `maximum_bytes_billed` — BigQuery samo przerwie
  zapytanie, gdyby przekroczyło budżet.

---

## Krok 11 — Wynik → zdanie → strumień SSE

**Streszczenie:** [`summarize`, pipeline.py:89](../../genai/pipeline.py#L89) — wiersze wyniku (maks. 20) wracają do modelu z instrukcją: odpowiedz **wyłącznie** na podstawie tych danych, w języku pytania.

**Serwer:** [api/main.py](../../api/main.py) · `stream_chat` ([:69](../../api/main.py#L69))

Zamiast czekać na całość, API wysyła **klatkę po każdym węźle grafu**, więc
użytkownik widzi postęp na żywo. Kontrakt jest w
[api/schemas.py](../../api/schemas.py) — warto go przeczytać w całości, ma 40
linii.

**Na co zwrócić uwagę:**

- **Odmowa to nie błąd** ([schemas.py:5](../../api/schemas.py#L5)): guardrail
  kończy protokół klatką `done` z `refused: true`, nie klatką `error`. Rozróżnia
  „nie chcę tego wykonać" od „coś się zepsuło".
- **Zawsze jedna klatka terminalna** ([main.py:82-89](../../api/main.py#L82)):
  nawet awaria w połowie strumienia kończy się klatką `error`, nie urwaniem
  połączenia. Frontend nigdy nie zawiśnie.
- **`get_pipeline` wołany wewnątrz `try`** ([:69-76](../../api/main.py#L69)):
  pipeline budowany jest leniwie, przy pierwszym pytaniu. Gdyby budowa padła
  (złe ADC, brak indeksu), użytkownik dostanie klatkę `error` zgodną z
  protokołem, a nie surowe 500.
- **`/health`** ([:90-125](../../api/main.py#L90)) sprawdza trzy zależności:
  Ollamę, BigQuery i obecność indeksu Chroma.

---

## Krok 12 — Frontend

**Pliki:** [frontend/src/api/chatClient.ts](../../frontend/src/api/chatClient.ts) → [streamParser.ts](../../frontend/src/api/streamParser.ts) → [hooks/useChatStream.ts](../../frontend/src/hooks/useChatStream.ts) → [components/StageTimeline.tsx](../../frontend/src/components/StageTimeline.tsx)

- **`chatClient.ts`** — używa `fetch` + `ReadableStream`, **nie `EventSource`**,
  bo `EventSource` obsługuje tylko GET, a my wysyłamy pytanie w ciele POST-a.
  Detal na końcu ([linie 21-25](../../frontend/src/api/chatClient.ts#L21)):
  domknięcie dekodera, żeby znak UTF-8 rozcięty między porcjami nie uciął
  ostatniej klatki.
- **`streamParser.ts`** — czysta funkcja: bierze kawałki tekstu, oddaje
  kompletne klatki. Buforuje, dopóki nie zobaczy `\n\n`. Bez I/O, więc testuje
  się trywialnie.
- **`StageTimeline.tsx`** — pokazuje kolejne etapy, żeby użytkownik widział, co
  system robi, zamiast gapić się na spinner.

---

## Krok 13 — Orkiestracja (obok ścieżki)

**Plik:** [dags/dbt_transform_dag.py](../../dags/dbt_transform_dag.py)

DAG Airflow z dwoma zadaniami: `dbt_run` → `dbt_test`. Uruchamiany ręcznie
(`schedule=None`) — pokazuje wzorzec orkiestracji, nie udaje produkcyjnego crona.

Dwa niebanalne szczegóły:

- **Kopiowanie projektu do katalogu tymczasowego**
  ([`_dbt_command`, :26](../../dags/dbt_transform_dag.py#L26)): zamontowany
  katalog `dbt/` należy do użytkownika hosta, a na Linuksie użytkownik `airflow`
  w kontenerze nie może do niego pisać — a `dbt deps` musi utworzyć
  `dbt_packages/`. Kopia rozwiązuje to raz na zawsze i czyni DAG przenośnym.
- **`seed` przed `run`** ([:56](../../dags/dbt_transform_dag.py#L56)): wymiary
  robią `ref()` do tabel-seedów, więc na świeżym datasecie `run` bez `seed` by
  padł.

---

## Gdzie jest…? (ściąga na rozmowę)

| Pytanie | Plik |
|---|---|
| Skąd biorą się dane? | [ingestion/download.py](../../ingestion/download.py) |
| Batch vs streaming? | [batch_load.py](../../ingestion/batch_load.py) vs [stream_producer.py](../../ingestion/stream_producer.py) + [stream_consumer.py](../../ingestion/stream_consumer.py) |
| Jak radzicie sobie z duplikatami? | [stg_trips.sql:86-103](../../dbt/models/staging/stg_trips.sql#L86) (dedup) + [stream_consumer.py:73](../../ingestion/stream_consumer.py#L73) (`insertId`) |
| Gdzie jest modelowanie wymiarowe? | [dbt/models/marts/](../../dbt/models/marts/) |
| Jak optymalizujecie koszt zapytań? | [fct_trips.sql:1-5](../../dbt/models/marts/fct_trips.sql#L1) + pomiar w [measure_partitioning.py](../../analysis/measure_partitioning.py) |
| Gdzie jest RAG? | [indexer.py](../../genai/indexer.py) (budowa) + [retriever.py](../../genai/retriever.py) (odczyt) |
| A jeśli model wygeneruje `DELETE`? | [guardrails.py:38-41](../../genai/guardrails.py#L38) |
| A jeśli wygeneruje zapytanie za 500 zł? | [guardrails.py:80-97](../../genai/guardrails.py#L80) (dry-run) + [pipeline.py:83](../../genai/pipeline.py#L83) |
| Co, gdy model się pomyli? | [pipeline.py:72-77](../../genai/pipeline.py#L72) (pętla retry) |
| Jak mierzycie jakość? | [genai/eval.py](../../genai/eval.py) + [docs/eval/latest.md](../eval/latest.md) |
| Gdzie są testy? | [tests/](../../tests/) — 105 testów |
| Jak to się uruchamia razem? | [docker-compose.yml](../../docker-compose.yml) (profile) |

## Trzy miejsca, które warto pokazać samemu

Jeśli masz pięć minut i chcesz pokazać kod, a nie slajdy:

1. **[stg_trips.sql:86-103](../../dbt/models/staging/stg_trips.sql#L86)** — dedup
   dwóch źródeł. Historia: strumień celowo dubluje wiadomości, klucz liczony jest
   z treści identycznie w Pythonie i w SQL-u, a sortowanie w `qualify` musi być
   deterministyczne, bo `pickup_datetime` siedzi w kluczu i remisuje.
2. **[guardrails.py:43-52](../../genai/guardrails.py#L43)** — `build_scope`.
   Historia: sprawdzanie nazw tabel wygląda na wystarczające, dopóki ktoś nie
   nazwie CTE tak samo jak prawdziwą tabelę.
3. **[pipeline.py:72-77](../../genai/pipeline.py#L72)** — krawędź wsteczna.
   Historia: to jedyny powód, dla którego to jest graf, a nie prosta funkcja —
   model dostaje powód odrzucenia i poprawia się w obrębie jednego pytania.

---

**Chcesz zrozumieć *dlaczego* tak, a nie inaczej?** → [00-caly-system.md](00-caly-system.md)
