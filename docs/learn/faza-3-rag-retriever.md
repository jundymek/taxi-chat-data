# Faza 3: RAG — indexer, few-shoty i retriever (notatka do nauki)

## Co to jest RAG i czemu tu wystarczy "RAG na schemacie"

RAG (Retrieval-Augmented Generation) to wzorzec, w którym przed wywołaniem
modelu językowego **doszukujemy** (retrieve) najbardziej pasujący kontekst
i wklejamy go do prompta. Model nie musi "pamiętać" naszej hurtowni — dostaje
ściągę na wejściu.

Klasyczny RAG indeksuje treść dokumentów (PDF-y, artykuły). U nas jest
prościej i taniej: **indeksujemy OPISY tabel, nie dane**. Żeby wygenerować
poprawny SQL, model nie potrzebuje ani jednego wiersza z BigQuery — potrzebuje
wiedzieć, że istnieje `marts.fct_trips` z kolumną `tip_amount` i że dzielnice
siedzą w `dim_location.borough`. To jest "RAG na schemacie": mały, statyczny
korpus (kilka tabel + kilkanaście przykładów), który mieści się w lokalnej
bazie wektorowej i kosztuje zero.

## Jak działa baza wektorowa

Trzy kroki:

1. **Embedding** — model embeddingowy (u nas `nomic-embed-text` przez Ollamę)
   zamienia tekst na wektor liczb, np. 768 wymiarów. Wektor to "współrzędne
   znaczenia": teksty o podobnym sensie lądują blisko siebie, nawet jeśli nie
   dzielą ani jednego słowa (dlatego "napiwek" znajdzie `tip_amount`).
2. **Podobieństwo kosinusowe** — odległość między wektorami mierzymy kątem.
   Pytanie użytkownika też embedujemy i pytamy bazę: "które dokumenty mają
   wektor najbliższy temu?".
3. **Top-k** — baza zwraca k najbliższych dokumentów. U nas domyślnie 4 opisy
   tabel i 3 przykłady — tyle, żeby prompt był treściwy, ale nie zaśmiecony.

Chroma w trybie embedded (`chromadb.PersistentClient`) trzyma wszystko w
katalogu `data/chroma/` — bez serwera, bez Dockera, bez sieci. Dla korpusu
rzędu dziesiątek dokumentów to idealny rozmiar narzędzia.

## Kolekcje: schemat oddzielnie od few-shotów

W Chromie mamy dwie kolekcje:

- `schema_docs` — po jednym dokumencie na model dbt ("Table marts.fct_trips:
  ... Columns: ..."),
- `few_shot_examples` — pary "QUESTION: ...\nSQL: ...".

Rozdzielenie jest celowe: to są **różne rodzaje kontekstu o różnej roli w
prompcie**. Opisy tabel mówią modelowi "co istnieje", przykłady mówią "jak się
tym posługiwać". Gdyby siedziały w jednej kolekcji, top-k mógłby zwrócić
5 przykładów i zero opisów tabel (albo odwrotnie) — a my chcemy gwarancję,
że w prompcie będzie i jedno, i drugie, w kontrolowanych proporcjach
(`k_schema=4`, `k_examples=3`).

## Po co few-shoty przy słabszym modelu

`gemma4` to mały, lokalny model — nie można liczyć na to, że "zna" dialekt
BigQuery i konwencje naszej hurtowni. Few-shot examples to kuratorowane,
ręcznie sprawdzone pary pytanie→SQL, które pokazują **wzorce**, nie fakty:

- jak wygląda pełna kwalifikacja tabel (`` `taxi-chat-data.marts.fct_trips` ``),
- jak JOIN-ować fakt z wymiarami (`f.payment_type = p.payment_type`),
- idiomy BigQuery (`COUNTIF`, `ROUND(AVG(...), 2)`).

Retriever dobiera przykłady **podobne do pytania**: pytanie o płatności
wyciągnie przykład z `dim_payment`, pytanie o dni tygodnia — ten z
`dim_datetime`. Model dostaje niemal gotowy szablon do adaptacji, zamiast
wymyślać JOIN-y od zera. Przy małych modelach to często większa dźwignia
jakości niż lepszy prompt systemowy.

## Czemu indeksacja to osobny krok

`python -m genai.indexer` uruchamiamy ręcznie, po zmianach w schemacie —
indeks NIE buduje się przy każdym pytaniu. Powody:

- **dbt YAML-e są jedynym źródłem prawdy.** Indexer czyta
  `dbt/models/**/*__models.yml` — te same pliki, z których dbt generuje
  dokumentację i testy. Zero ręcznego duplikowania opisów; jak ktoś doda
  kolumnę w YAML-u, reindeksacja podnosi ją automatycznie.
- **Koszt i determinizm.** Embeddingi liczą się raz przy indeksacji, a nie
  przy każdym zapytaniu. W czasie pytania embedujemy tylko samo pytanie.
- **Przebudowa od zera** (`delete_collection` + `create_collection`) zamiast
  dokładania — usunięte modele i przykłady znikają z indeksu, nie zostają
  osierocone dokumenty.
- Dataset `raw` celowo NIE jest indeksowany — model ma go "nie widzieć"
  (a guardraile i tak by go zablokowały). Least privilege zaczyna się już na
  poziomie tego, co model wie.

## Czemu w testach wstrzykujemy FakeEmbedder

`build_index(embedder=None)` i `Retriever(embedder=None)` domyślnie tworzą
prawdziwego `LLMClient` (leniwy import w środku funkcji), ale testy podają
własny obiekt z metodą `embed`. FakeEmbedder zwraca deterministyczne wektory
2-wymiarowe: teksty z "trip" → `[1, 0]`, reszta → `[0, 1]`. Dzięki temu:

- **Determinizm** — wiemy z góry, który dokument jest "najbliższy", więc
  asercje są ścisłe (`ctx.tables == [...]`), nie "jakoś podobne".
- **Zero zależności** — testy nie wymagają działającej Ollamy ani sieci;
  przechodzą na CI i na każdej maszynie w ułamku sekundy.
- **Testujemy naszą logikę, nie cudzą** — czy dobrze czytamy YAML-e, budujemy
  kolekcje i przycinamy `k` do rozmiaru kolekcji. Jakość samych embeddingów to
  problem modelu, nie tego modułu (zweryfikuje ją test integracyjny w Task 5).

To jest dependency injection w najprostszej postaci: parametr z domyślną
wartością `None` + leniwy import. Duck typing załatwia resztę — wystarczy
"coś z metodą `embed(texts) -> list[list[float]]`", bez interfejsów i mocków
z bibliotek.
