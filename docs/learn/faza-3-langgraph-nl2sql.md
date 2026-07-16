# Faza 3: LangGraph + NL2SQL — jak spięliśmy pipeline "chat with data"

## Czym jest LangGraph i czym różni się od LangChain

LangChain popularyzował "chainy": liniowe sekwencje kroków (prompt → LLM →
parser → ...). Chain działa świetnie, dopóki przepływ jest prostą rurą. Nasz
przepływ prostą rurą **nie jest** — po walidacji SQL-a musimy czasem *wrócić*
do generowania (retry z feedbackiem). Liniowy chain nie ma naturalnego sposobu
na cykl.

LangGraph modeluje przepływ jako **graf stanów** (state machine): węzły to
funkcje, krawędzie mówią "co dalej", a krawędzie warunkowe wybierają następny
węzeł na podstawie aktualnego stanu. Cykle są legalne i pierwszoklasowe — to
dokładnie ten jeden feature, dla którego bierzemy bibliotekę zamiast pisać
pętlę `while` ręcznie: graf jest deklaratywny, testowalny i czytelny jako
diagram.

## Nasz graf

```
retrieve → generate_sql → validate ──ok──→ execute → summarize → END
                ↑              │
                └──retry───────┤ (attempts < MAX_SQL_ATTEMPTS)
                               └──wyczerpane──→ refuse → END
```

- **retrieve** — Retriever (Chroma) zwraca `SchemaContext`: opisy tabel
  i podobne few-shoty dla pytania.
- **generate_sql** — składa prompt (kontekst + pytanie + ewentualny feedback
  błędu) i woła LLM; zlicza próby.
- **validate** — guardraile z Task 3: parsowanie sqlglot, tylko SELECT,
  allowlista datasetów, LIMIT, dry-run BigQuery.
- **krawędź warunkowa** (`route_after_validate`) — trzy wyjścia: `execute`
  (SQL ok), `generate_sql` (odrzucony, ale mamy jeszcze próby — **to jest ta
  pętla**), `refuse` (limit prób wyczerpany).
- **execute** — realny job BigQuery, zawsze z `maximum_bytes_billed` (pas
  bezpieczeństwa niezależny od dry-runu).
- **summarize** — LLM streszcza wiersze wyniku po polsku.
- **refuse** — grzeczna polska odmowa z ostatnim powodem odrzucenia.

Kluczowy pomysł: przy odrzuceniu polski `reason` z guardraili wraca do modelu
jako feedback ("poprzednia próba odrzucona: Brak LIMIT"). Model nie zgaduje
w ciemno drugi raz — dostaje konkretną przyczynę. To tania forma
self-correction, która realnie podnosi skuteczność NL2SQL.

## Stan jako TypedDict i częściowe update'y

Stan grafu to `TypedDict` (`AskState`) z `total=False` — każde pole opcjonalne.
Węzeł **nie zwraca całego stanu**, tylko słownik z polami, które zmienił
(np. `{"sql": ..., "attempts": 2}`). LangGraph robi merge takiego częściowego
update'u z dotychczasowym stanem. Zalety:

- węzły są małe, czyste funkcje `stan → delta` — trywialne do testowania,
- nie da się przypadkiem zgubić pola, którego węzeł nie dotyka,
- typowanie dokumentuje kontrakt: kto co czyta, kto co pisze.

`TypedDict` zamiast dataclassy, bo LangGraph merguje słowniki — dostajemy
walidację kluczy w edytorze bez pisania własnej logiki merge.

## Anatomia prompta NL2SQL

Prompt składa się z czterech warstw (w tej kolejności):

1. **System prompt** — rola i twarde reguły: jeden SELECT w fence `sql`,
   tylko tabele z kontekstu, pełna kwalifikacja
   `taxi-chat-data.<dataset>.<table>`, zakaz modyfikacji danych.
2. **Kontekst RAG** — opisy tabel/kolumn wyciągnięte z Chroma pod to
   konkretne pytanie (a nie cały schemat — mniejszy prompt, mniej halucynacji).
3. **Few-shoty** — podobne rozwiązane pary "QUESTION → SQL"; model dużo
   lepiej naśladuje wzorzec niż wykonuje abstrakcyjne instrukcje.
4. **Feedback błędu** (tylko przy retry) — powód ostatniego odrzucenia
   z wyraźnym "fix the SQL accordingly".

Reguły po angielsku (modele radzą sobie z nimi lepiej), pytanie i komunikaty
dla użytkownika po polsku.

## Czemu SQL wyciągamy regexem i zdejmujemy średnik

LLM-y "opakowują" odpowiedź: "Sure! ```sql ... ``` Hope it helps." Regex
szuka najpierw fence'a ```` ```sql ````, potem gołego ```` ``` ````, a gdy
fence'a brak — bierze cały tekst. Średnik na końcu zdejmujemy, bo:

- sqlglot parsuje `SELECT 1;` jako potencjalnie wiele statementów, a nasze
  guardraile wymagają dokładnie jednego,
- dosklejanie `LIMIT` do SQL-a zakończonego średnikiem dałoby błąd składni.

To celowo prymitywny parser: deterministyczny, szybki i wystarczający, bo
i tak każdy wynik przechodzi przez pełną walidację AST w guardrailach —
regex nie jest tu warstwą bezpieczeństwa, tylko wygody.

## Dependency injection w build_pipeline

`build_pipeline(llm=None, retriever=None, validate_fn=None, bq_client=None)` —
każda zależność ma produkcyjny default tworzony **leniwie** (import w środku
funkcji), ale testy wstrzykują fake'i: `FakeLLM` z kolejką odpowiedzi,
`FakeRetriever` ze stałym kontekstem, `FakeBQClient` liczący wykonane
zapytania. Efekt:

- unit testy przechodzą bez Ollamy, bez GCP, w ułamku sekundy,
- testujemy logikę *grafu* (routing, retry, licznik prób), nie integracje,
- `FakeBQClient.query` asercją wymusza `maximum_bytes_billed` — kontrakt
  kosztowy jest sprawdzany w teście, nie tylko w code review.

Prawdziwe integracje (Ollama + Chroma + BigQuery) mają osobne testy
`@pytest.mark.integration`, domyślnie deselektowane — odpalane ręcznie
w Task 5, kiedy indeks Chroma już istnieje.
