# Cały system od zera — przewodnik po taxi-chat-data

Notatka do nauki (PL). Ten dokument jest inny niż pozostałe w `docs/learn/`: tamte
opisują pojedyncze zadania, ten spina wszystko w całość. Czytaj od góry — każda
sekcja zakłada poprzednią.

**Do czego służy:** żebyś potrafił opowiedzieć o tym projekcie na rozmowie
kwalifikacyjnej i obronić każdą decyzję, którą podjęliśmy.

---

## 1. Co to w ogóle jest

Aplikacja, w której **pytasz o dane zwykłym językiem i dostajesz odpowiedź**.

Wpisujesz „Ile było przejazdów?" → dostajesz „Było 2 998 748 przejazdów."

Pod spodem siedzą ~3 miliony przejazdów nowojorskich taksówek ze stycznia 2023.
Między Twoim pytaniem a odpowiedzią dzieje się osiem rzeczy, które opisuje ten
dokument.

**Dlaczego to niebanalne:** żeby odpowiedzieć, system musi zamienić polskie
zdanie na zapytanie SQL, wykonać je na bazie i przetłumaczyć wynik z powrotem na
zdanie. Każdy z tych kroków może pójść źle na inny sposób.

---

## 2. Cztery klocki i jak do siebie pasują

Cały projekt to cztery bloki. Reszta to szczegóły implementacyjne.

```
[1] INGESTIA        [2] HURTOWNIA        [3] GENAI          [4] APLIKACJA
surowe dane    →    uporządkowane   →   pytanie→SQL   →   API + frontend
                     dane

Parquet/Pub-Sub     BigQuery + dbt      Ollama + RAG       FastAPI + React
```

Kolejność ma znaczenie i jest celowa: **najpierw miej z czego pytać**, dopiero
potem buduj pytanie. Dlatego GenAI powstało w Fazie 3, a nie w Fazie 1 — bez
uporządkowanej hurtowni nie miałoby o co pytać.

Poniżej każdy blok osobno.

---

## 3. Blok [1] — skąd się biorą dane

### Dwie drogi do bazy

**Droga wsadowa (batch)** — [ingestion/batch_load.py](../../ingestion/batch_load.py)

Miasto Nowy Jork publikuje pliki Parquet, jeden na miesiąc. Bierzemy jeden
(styczeń 2023, ~3 mln wierszy), wrzucamy do GCS i ładujemy do BigQuery.

- **Parquet** — format pliku do danych analitycznych. W przeciwieństwie do CSV
  jest *kolumnowy*: dane jednej kolumny leżą obok siebie. Dzięki temu zapytanie
  „daj mi tylko kwoty" nie musi czytać całej reszty. Jest też skompresowany.
- **GCS (Google Cloud Storage)** — „dysk w chmurze". Tu pełni rolę **data lake**:
  miejsca, gdzie surowe pliki leżą w oryginalnej postaci, zanim je przetworzymy.

**Droga strumieniowa (streaming)** — [ingestion/stream_producer.py](../../ingestion/stream_producer.py) + [stream_consumer.py](../../ingestion/stream_consumer.py)

Udajemy, że dane płyną na żywo: producent odczytuje ten sam Parquet i wysyła
wiersze pojedynczo do kolejki Pub/Sub (z opóźnieniem, żeby wyglądało jak strumień),
konsument je odbiera i dopisuje do BigQuery.

- **Pub/Sub** — kolejka komunikatów. Producent wrzuca wiadomość, konsument
  odbiera. Rozdziela nadawcę od odbiorcy: producent nie musi wiedzieć, kto czyta.

**Dlaczego oba?** Bo w prawdziwej firmie występują oba naraz: historia ładowana
raz na dobę wielką paczką, plus bieżące zdarzenia płynące na żywo. Projekt miał
pokazać, że rozumiesz różnicę.

### Pułapka, którą specjalnie wbudowaliśmy

Producent **celowo wysyła niektóre wiersze dwa razy**. To nie błąd — to
symulacja realnego problemu: w systemach kolejkowych obowiązuje gwarancja
*at-least-once* („dostarczę przynajmniej raz"), więc duplikaty są normą, nie
wyjątkiem. Blok [2] musi sobie z nimi poradzić — i radzi.

---

## 4. Blok [2] — hurtownia, czyli porządkowanie

Tu jest najwięcej pojęć branżowych. Po kolei.

### Trzy warstwy: raw → staging → marts

To standard w inżynierii danych (spotkasz też nazwy bronze/silver/gold).

| Warstwa | Co zawiera | Po co |
|---|---|---|
| `raw` | dane 1:1 jak przyszły, nietknięte | Żeby móc zawsze wrócić do oryginału |
| `staging` | oczyszczone, przetypowane, bez duplikatów | Jedno miejsce na „sprzątanie" |
| `marts` | model gwiazdy, gotowy do pytań | To, o co faktycznie pytamy |

**Dlaczego nie od razu do celu?** Bo gdy coś pójdzie źle, chcesz wiedzieć *na
którym etapie*. Jeśli czyszczenie i modelowanie robisz w jednym kroku, każdy błąd
wymaga przeładowania wszystkiego od zera. Warstwy dają punkty kontrolne.

### Co robi warstwa staging

Plik [dbt/models/staging/stg_trips.sql](../../dbt/models/staging/stg_trips.sql):

1. **Scala oba źródła** — `raw` (batch) i `stream.trips` (streaming) przez `UNION`.
2. **Czyści** — wyrzuca wiersze z ujemną kwotą, zerowym dystansem, datą spoza zakresu.
3. **Przetypowuje** — teksty na daty, liczby zmiennoprzecinkowe na całkowite.
4. **Usuwa duplikaty** — i tu dzieje się rzecz warta zrozumienia.

**Klucz zastępczy (surrogate key).** Dane nie mają identyfikatora przejazdu.
Dlatego liczymy `trip_key` — skrót (hash) z kilku pól: czasu odbioru, lokalizacji,
kwoty. Dwa identyczne wiersze dają identyczny hash, więc duplikat da się wykryć.
Potem `qualify row_number() over (partition by trip_key ...) = 1` zostawia
z każdej grupy jeden wiersz.

Jest tam jeszcze jeden niuans warty zrozumienia — `source_rank`. Ten sam przejazd
może dotrzeć **obiema drogami**: batchem i strumieniem. Który wiersz wygrywa?
Nadajemy batchowi rangę 0, strumieniowi 1 i sortujemy po niej — batch jest
źródłem autorytatywnym, więc wygrywa. Bez tego BigQuery wybrałby zwycięzcę
losowo i `stg_trips` zmieniałby się przy każdym przebudowaniu, mimo że dane
wejściowe są te same. Ostateczne rozstrzygnięcie remisów robi
`to_json_string()` — daje wynik zależny wyłącznie od treści wiersza.

To rozwiązuje problem z sekcji 3: duplikaty wstrzyknięte przez producenta nigdy
nie docierają do martów.

### Model gwiazdy (star schema)

W `marts/` mamy pięć tabel:

```
        dim_datetime      dim_location
              \               /
               \             /
                fct_trips  ←  (fakty: 3 mln wierszy)
               /             \
              /               \
        dim_payment      dim_ratecode
```

- **Tabela faktów** (`fct_trips`) — zdarzenia. Duża, wąska, dużo wierszy.
  Jeden wiersz = jeden przejazd.
- **Tabele wymiarów** (`dim_*`) — słowniki opisujące fakty. Małe, szerokie.
  `dim_location` mówi, że strefa 132 to „JFK Airport".

**Dlaczego tak, a nie jedna wielka tabela?** Bo `dim_location` ma ~265 wierszy.
Gdyby nazwę strefy trzymać przy każdym przejeździe, powtórzyłaby się 3 miliony
razy. Rozdzielenie oszczędza miejsce i — ważniejsze — daje jedno miejsce na
poprawkę, gdy nazwa strefy się zmieni.

Kształt nazywa się gwiazdą, bo fakty są w środku, a wymiary „promieniują" wokół.

### Partycjonowanie i klastrowanie

W [fct_trips.sql](../../dbt/models/marts/fct_trips.sql) na górze jest:

```sql
partition_by={'field': 'pickup_date', 'data_type': 'date'},
cluster_by=['pickup_location_id']
```

- **Partycjonowanie** — fizyczny podział tabeli na kawałki wg daty. Zapytanie
  „przejazdy z 15 stycznia" czyta jedną partycję zamiast całej tabeli.
- **Klastrowanie** — w obrębie partycji dane są posortowane wg lokalizacji, więc
  filtr po strefie też czyta mniej.

**Po co w projekcie, skoro dane są małe?** Bo w BigQuery **płacisz za
przeskanowane bajty**. Mniej skanu = niższy rachunek. Przy 3 mln wierszy to
grosze, ale technika jest ta sama przy miliardach. Efekt zmierzyliśmy —
[analysis/measure_partitioning.py](../../analysis/measure_partitioning.py).

### Czym jest dbt

**dbt** (data build tool) to narzędzie, w którym transformacje danych pisze się
jako **zwykłe pliki SQL** — a dbt zamienia je w tabele we właściwej kolejności.

Trzy rzeczy, które daje:

1. **Zależności same się układają.** Piszesz `{{ ref('stg_trips') }}` zamiast
   nazwy tabeli, a dbt wie, że `stg_trips` musi powstać wcześniej. Buduje graf
   zależności i wykonuje po kolei.
2. **Testy.** W plikach YAML deklarujesz „ta kolumna nie może być pusta",
   „ta musi być unikalna". `dbt test` to sprawdza. Tak weryfikujemy, że dedup
   z `trip_key` naprawdę działa.
3. **Dokumentacja przy kodzie.** Opisy modeli i kolumn są w YAML obok SQL —
   i, co ważne dla bloku [3], **są jedynym źródłem prawdy o schemacie**.

---

## 5. Blok [3] — GenAI, czyli serce projektu

Tu odpowiadamy na pytanie: jak „Ile było przejazdów?" staje się poprawnym SQL-em.

### Problem: model językowy nie zna Twojej bazy

Ollama z modelem `gemma4` potrafi pisać SQL — ale nie ma pojęcia, że masz tabelę
`fct_trips` z kolumną `pickup_date`. Gdyby zgadywał, wygenerowałby SQL na
nieistniejących tabelach.

Trzeba mu **podać schemat**. Ale nie cały naraz — przy dużej bazie schemat się
nie zmieści, a nadmiar kontekstu pogarsza wyniki.

### Rozwiązanie: RAG

**RAG (Retrieval-Augmented Generation)** — „generowanie wspomagane wyszukiwaniem".
Zamiast wrzucać modelowi całą wiedzę, **wyszukujesz tylko fragmenty pasujące do
pytania** i dokładasz je do promptu.

Jak to działa u nas:

**Krok 1 — indeksowanie** (raz, [genai/indexer.py](../../genai/indexer.py)):
Bierzemy opisy modeli z YAML-i dbt (te z sekcji 4!) i zamieniamy każdy na
**embedding** — wektor liczb reprezentujący znaczenie tekstu. Zapisujemy w Chromie.

**Krok 2 — wyszukiwanie** (przy każdym pytaniu, [genai/retriever.py](../../genai/retriever.py)):
Twoje pytanie też zamieniamy na embedding i szukamy najbliższych wektorów.
„Ile było przejazdów?" trafia w opis `fct_trips`, nie w `dim_payment`.

- **Embedding** — tekst zamieniony na listę liczb tak, żeby teksty o podobnym
  znaczeniu miały podobne liczby. Robi to osobny model, `nomic-embed-text`.
- **Baza wektorowa (Chroma)** — baza, która zamiast „znajdź wiersz o id=5" umie
  „znajdź 5 najbardziej podobnych wektorów".

**Kluczowy szczegół:** indeksujemy opisy z dbt, **nic nie przepisujemy ręcznie**.
Zmienisz opis kolumny w dbt → przeindeksujesz → model od razu wie o zmianie.
Gdyby schemat był przepisany do promptu na sztywno, rozjechałby się przy
pierwszej zmianie.

### Guardrails, czyli nadzorca

Model wygenerował SQL. **Nie wykonujemy go od razu** — najpierw
[genai/guardrails.py](../../genai/guardrails.py) sprawdza pięć rzeczy:

| Sprawdzenie | Przed czym chroni |
|---|---|
| Czy to poprawny SQL? | Model czasem generuje śmieci |
| Czy to jedno zapytanie? | `SELECT 1; DROP TABLE x` — dwa polecenia |
| Czy to `SELECT`? | Blokuje `DELETE`, `UPDATE`, `DROP` |
| Czy tabele są dozwolone? | Tylko `staging` i `marts`, nigdy `raw` |
| Ile bajtów przeskanuje? | Odrzuca zapytania >1 GB |

Trzy rzeczy warte uwagi:

**Parsujemy, nie szukamy słów.** Sprawdzenie „czy w tekście jest DROP" da się
obejść (`/**/DROP`, `dRoP`). My parsujemy SQL biblioteką `sqlglot` i patrzymy na
*strukturę* — czy korzeń drzewa to `SELECT`. Tego nie da się oszukać formatowaniem.

**Świadomość zakresu (scope).** W kodzie jest komentarz o CTE. Chodzi o atak:
`WITH trips AS (SELECT * FROM trips) SELECT * FROM trips` — zewnętrzne `trips` to
niewinne CTE, ale wewnętrzne to prawdziwa tabela. Naiwne sprawdzenie po nazwie by
to przepuściło. Używamy `build_scope`, które odróżnia jedno od drugiego.

**Dry-run.** Ostatni krok pyta BigQuery: *„ile bajtów przeczytałoby to zapytanie,
gdybym je wykonał?"* — i odrzuca powyżej 1 GB. To jedyne zabezpieczenie działające
**zanim** powstanie koszt. Nie ma go w zwykłych bazach.

Dodatkowo: jeśli w zapytaniu nie ma `LIMIT`, dopisujemy `LIMIT 100`.

### LangGraph — spinacz

[genai/pipeline.py](../../genai/pipeline.py) opisuje cały przepływ jako **graf
stanu**:

```
retrieve → generate_sql → validate → ┬→ execute → summarize → KONIEC
                             ↑       ├→ refuse ───────────→ KONIEC
                             └───────┘  (powrót z błędem)
```

Sześć kroków. Cała wartość siedzi w **strzałce powrotnej**: jeśli guardrails
odrzucą SQL, wracamy do generowania — ale tym razem model dostaje *komunikat
błędu* i próbuje ponownie. Do trzech razy.

To dlatego w ewaluacji widnieje „średnio 1.44 próby" — czasem za pierwszym
razem, czasem za drugim.

**Uczciwie:** przy sześciu krokach LangGraph nie jest niezbędny — to samo dałoby
się napisać pętlą `while`. Wybraliśmy go, bo jest wymieniany w ofertach pracy
i daje czytelny diagram. To decyzja pod portfolio, nie konieczność techniczna.

### Ewaluacja — skąd wiemy, że działa

[genai/eval.py](../../genai/eval.py): 18 pytań, do każdego ręcznie napisany
wzorcowy SQL. Puszczamy pytanie przez system i **porównujemy wyniki** (nie teksty
SQL — dwa różne zapytania mogą dać ten sam poprawny wynik).

Rezultat: gemma4 67% trafności, llama3.1:8b 61%.

**Dlaczego to ważne:** bez pomiaru „działa" jest opinią. Z pomiarem wiesz, że
w co trzecim pytaniu się myli — i możesz o tym uczciwie napisać w README.

---

## 6. Blok [4] — API i frontend

Najprostsza warstwa.

- [api/main.py](../../api/main.py) — FastAPI. Endpoint `POST /chat` przyjmuje
  pytanie i **streamuje** odpowiedź przez SSE (Server-Sent Events), wysyłając
  informację po każdym kroku grafu: „retrieve", „generate_sql", „execute"...
- Frontend pokazuje te kroki na żywo — jak śledzenie przesyłki.

**Dlaczego streaming, a nie zwykłe żądanie?** Bo cały przebieg trwa kilka-kilkanaście
sekund. Bez sygnałów pośrednich użytkownik patrzy na zawieszony ekran i nie wie,
czy coś się dzieje.

---

## 7. Infrastruktura — co gdzie chodzi

```
TWÓJ LAPTOP (host)                     CHMURA (GCP)
├── Ollama :11434  ← modele AI         ├── GCS       (surowe pliki)
├── Vite   :3002   ← frontend          ├── BigQuery  (hurtownia)
└── Docker                             └── Pub/Sub   (kolejka)
    ├── profil api      :8000
    ├── profil airflow  :8080
    └── profil dbt      (jednorazowo)
```

**Dlaczego Ollama na hoście, a nie w kontenerze?** Dwa powody: kontener na macOS
nie ma dostępu do GPU (byłoby wolno), a modele ważą ~10 GB i musiałyby się
pobrać drugi raz. Kontenery sięgają do niej przez `host.docker.internal`.

**Profile compose** — jedno `docker compose up` nie startuje nic. Wybierasz
świadomie: `--profile api`, `--profile airflow`, `--profile dbt`.

**Airflow** — orkiestrator. Uruchamia `dbt run` → `dbt test` jako graf zadań,
z logami i statusem. U nas ręcznie wyzwalany, bez harmonogramu — chodzi
o pokazanie wzorca, nie o produkcyjny scheduler.

**ADC (Application Default Credentials)** — sposób uwierzytelniania w GCP bez
plików z kluczami. Logujesz się raz przez `gcloud`, a biblioteki same znajdują
poświadczenia. Dlatego w repo **nie ma żadnego klucza** — i gitleaks pilnuje,
żeby nie było.

---

## 8. Prześledzenie jednego pytania

Wpisujesz „Ile było przejazdów?". Co się dzieje:

| # | Gdzie | Co |
|---|---|---|
| 1 | `api/main.py` | Przyjmuje pytanie, otwiera strumień SSE |
| 2 | `retriever.py` | Zamienia pytanie na embedding (Ollama), szuka w Chromie → znajduje opis `fct_trips` |
| 3 | `nl2sql.py` | Buduje prompt: pytanie + znaleziony schemat + przykłady → wysyła do gemma4 |
| 4 | gemma4 | Zwraca `SELECT COUNT(*) AS trip_count FROM \`taxi-chat-data.marts.fct_trips\`` |
| 5 | `guardrails.py` | Parsuje, sprawdza pięć reguł, dopisuje `LIMIT 100`, robi dry-run → 0 GB, OK |
| 6 | BigQuery | Wykonuje zapytanie → `2998748` |
| 7 | `pipeline.py` | Wysyła wynik do gemma4: „ubierz to w zdanie po polsku" |
| 8 | frontend | „Było 2 998 748 przejazdów." + pokazany SQL i koszt skanu |

Gdyby krok 5 odrzucił SQL, wracamy do kroku 3 z komunikatem błędu.

---

## 9. Decyzje i alternatywy

Najczęstsze pytanie na rozmowie: *„dlaczego tak, a nie inaczej?"*

| Decyzja | Alternatywa | Dlaczego tak |
|---|---|---|
| BigQuery | Postgres | Hurtownia kolumnowa, partycjonowanie, dry-run kosztowy. Wymóg oferty. |
| Ollama lokalnie | OpenAI/Anthropic API | 0 zł, dane nie wychodzą z laptopa. Kosztem: gorsza trafność (67% vs ~90%). |
| dbt | Czysty SQL w skryptach | Graf zależności, testy, dokumentacja jako źródło prawdy dla RAG. |
| Chroma | pgvector | Lokalna, zero konfiguracji. pgvector miałby sens przy Postgresie. |
| LangGraph | Pętla `while` | Wymóg ofert + czytelny diagram. Technicznie zbędny przy 6 krokach. |
| Guardrails z parsowaniem | Filtr słów kluczowych | Filtra słów nie da się obronić — obejście przez formatowanie. |
| Jeden miesiąc danych | Cały rok | Darmowy limit BigQuery. Skalowanie to zmiana jednej zmiennej. |
| Airflow lokalnie | Cloud Composer | Composer kosztuje ~$300/mies. Wzorzec ten sam. |

---

## 10. Czego świadomie nie ma

- **Neo4j / graf** — odłożone od początku jako „miło mieć". Nie zmieniłoby
  kształtu potoku.
- **Skonteneryzowane API nie serwuje `/eval` ani frontendu** — `docs/` i
  `frontend/dist` są wykluczone z obrazu. `/chat` działa.
- **`dbt test` nie działa w CI** — bo CI świadomie nie ma poświadczeń GCP.
  Testy schematu chodzą lokalnie i w Airflow.
- **Model myli się w ~1/3 pytań** — to realny stan darmowych modeli lokalnych.
  Dlatego zmierzyliśmy, zamiast zapewniać, że „działa świetnie".

---

## 11. Pojęcia — ściąga

| Pojęcie | Jednym zdaniem |
|---|---|
| **Data lake** | Miejsce na surowe pliki w oryginalnej postaci (u nas GCS). |
| **Hurtownia** | Baza zoptymalizowana pod analizę, nie pod zapis (BigQuery). |
| **Batch vs streaming** | Wielka paczka raz na jakiś czas vs zdarzenia na bieżąco. |
| **At-least-once** | Gwarancja kolejki: dostarczę przynajmniej raz — więc licz się z duplikatami. |
| **Staging** | Warstwa czyszcząca między surowym a gotowym. |
| **Model gwiazdy** | Tabela faktów w środku + tabele wymiarów wokół. |
| **Klucz zastępczy** | Sztuczny identyfikator (u nas hash), gdy dane nie mają własnego. |
| **Partycjonowanie** | Fizyczny podział tabeli, żeby czytać mniej. |
| **dbt** | SQL + graf zależności + testy + dokumentacja. |
| **Embedding** | Tekst zamieniony na wektor liczb oddający znaczenie. |
| **Baza wektorowa** | Baza szukająca po podobieństwie, nie po równości. |
| **RAG** | Wyszukaj pasujące fragmenty i dołóż do promptu przed generowaniem. |
| **NL2SQL** | Zamiana pytania w języku naturalnym na SQL. |
| **Guardrails** | Warstwa sprawdzająca wyjście modelu, zanim coś zrobi. |
| **Dry-run** | Zapytanie o koszt zapytania bez jego wykonania. |
| **SSE** | Jednokierunkowy strumień z serwera do przeglądarki. |
| **ADC** | Uwierzytelnianie w GCP bez plików z kluczami. |
| **Orkiestracja** | Uruchamianie kroków we właściwej kolejności (Airflow). |

---

## 12. Jak sprawdzić, czy rozumiesz

Odpowiedz sobie bez zaglądania:

1. Dlaczego dane przechodzą przez `staging`, zamiast iść z `raw` prosto do `marts`?
2. Skąd system wie, że istnieje tabela `fct_trips` — kto mu to powiedział?
3. Co się stanie, gdy model wygeneruje `DROP TABLE fct_trips`? Który kod to zatrzyma?
4. Dlaczego producent strumienia celowo wysyła duplikaty i co je usuwa?
5. Czemu Ollama nie jest w Dockerze, skoro reszta jest?
6. Co oznacza „średnio 1.44 próby" w wynikach ewaluacji?

Jeśli na którekolwiek nie umiesz odpowiedzieć — to jest miejsce, do którego warto
wrócić w tym dokumencie.
