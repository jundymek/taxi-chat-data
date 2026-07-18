# Faza 6 — Ewaluacja NL2SQL (notatka do nauki)

Ta notatka tłumaczy, jak i dlaczego mierzymy jakość modeli językowych w naszym
pipeline „pytanie po polsku → SQL → odpowiedź". Kod: `genai/eval.py`,
pytania: `genai/eval_questions.yml`.

## Problem: jak ocenić NL2SQL?

Model dostaje pytanie („Ile było przejazdów?") i generuje SQL. Chcemy wiedzieć,
który model (gemma4 vs llama3.1) radzi sobie lepiej. Naiwny pomysł: porównać
wygenerowany SQL z „poprawnym" SQL tekst-do-tekstu. **To zły pomysł** — istnieje
nieskończenie wiele równoważnych zapytań dających ten sam wynik:

```sql
SELECT COUNT(*) FROM trips
SELECT COUNT(1) AS n FROM trips
SELECT SUM(1) FROM `...trips`
```

Wszystkie są poprawne, ale różnią się znakami. Porównanie tekstu SQL karałoby
model za styl, nie za poprawność.

## Rozwiązanie: porównujemy WYNIKI, nie zapytania

Dla każdego pytania trzymamy **referencyjny SQL** (ręcznie zweryfikowany — „złota
prawda"). Uruchamiamy oba zapytania na BigQuery i porównujemy zbiory wierszy:

- **Odpowiedź modelu** — pipeline generuje SQL, wykonuje go, zwraca wiersze.
- **Złota prawda** — nasz referencyjny SQL wykonany na tej samej hurtowni.

Jeśli zbiory wierszy są równe → model odpowiedział poprawnie, niezależnie od tego,
jak napisał zapytanie. To jest funkcja `result_sets_match`.

### Dwie subtelności w porównaniu wyników

1. **Niewrażliwość na kolejność.** `[{zone: A}, {zone: B}]` i
   `[{zone: B}, {zone: A}]` to ten sam wynik — SQL bez `ORDER BY` nie gwarantuje
   kolejności. Traktujemy wiersze jak **multizbiór** (zliczamy wystąpienia przez
   `collections.Counter`), więc kolejność nie ma znaczenia.
2. **Tolerancja numeryczna.** `4.16` i `4.160000001` to praktycznie ta sama
   średnia — różnice biorą się z zaokrągleń zmiennoprzecinkowych. Porównujemy
   liczby z tolerancją (`abs_tol`), zaokrąglając do wspólnej „siatki" przed
   porównaniem. Stringi i wartości logiczne porównujemy dokładnie.

`result_sets_match` jest **czystą funkcją** — bez BigQuery, bez sieci — więc
testujemy ją w pełni jednostkowo (`tests/test_eval.py`).

## Skąd bierze się „złota prawda"?

Z `genai/eval_questions.yml`: lista par (pytanie, referencyjny SQL). Kluczowa
zasada bezpieczeństwa: **każdy referencyjny SQL pyta tylko o `marts.*`** (dozwolone
przez guardraile — `config.ALLOWED_DATASETS = {staging, marts}`), nigdy o `raw`
czy `stream`. Dzięki temu referencja działa pod tymi samymi regułami co pipeline,
a ocena jest uczciwa. Kolumny i JOIN-y zweryfikowane względem modeli dbt
(`fct_trips` + wymiary `dim_location/dim_payment/dim_ratecode/dim_datetime`).

## Odmowy (refusals) jako poprawne odpowiedzi

Niektóre pytania modele **powinny odrzucić** — np. „Usuń wszystkie dane" albo
„Pokaż surowe wiersze z raw.trips". Guardraile blokują takie zapytania. W eval
oznaczamy je `expects_refusal: true`. Reguła w `evaluate_case`:

> Odmowa jest poprawna **wtedy i tylko wtedy**, gdy jej oczekiwaliśmy.

Czyli: odmowa na „Usuń dane" = poprawnie (bezpieczeństwo działa); odmowa na
„Ile przejazdów?" = błąd (model nie poradził sobie z legalnym pytaniem).

## Wstrzykiwanie modelu (dependency injection)

Nie duplikujemy logiki pipeline'u dla każdego modelu. Używamy istniejącej fabryki
`build_pipeline(llm=LLMClient(model=...))` — podmieniamy tylko klienta LLM.
`evaluate_model` przyjmuje `pipeline_factory`, więc w testach wstrzykujemy
**atrapę** (`FakePipeline` + `FakeBQ`), a w produkcji prawdziwy pipeline. To
klasyczny wzorzec DI: ta sama funkcja, różne zależności, zero mocków w kodzie
produkcyjnym.

## Metryki w raporcie

Na model liczymy: **Trafność** (% pytań z poprawnym wynikiem), **Wykonane**
(% pytań, które w ogóle wykonały SQL, bez odmowy), **Śr. próby** (średnia liczba
prób generacji SQL — pipeline ponawia po błędzie walidacji, max 3), **Odmowy**
(ile pytań odrzucono).

## Dlaczego `/eval` czyta raport zamiast liczyć na żądanie?

Endpoint `GET /eval` w API tylko **odczytuje** ostatni zapisany raport
(`docs/eval/latest.json`). Nie uruchamia ewaluacji — pełny przebieg to minuty
pracy dwóch modeli LLM + zapytania do BigQuery (koszt, czas, wolne). Żądanie HTTP
musi być szybkie i tanie, więc ciężką pracę robimy offline (`python -m genai.eval`,
krok operatora), a API serwuje gotowy wynik. Gdy raportu nie ma, endpoint zwraca
czytelny stan „brak raportu" zamiast błędu.

## Podsumowanie

- Oceniaj **wyniki**, nie tekst zapytań — równoważne SQL-e dają ten sam wynik.
- Porównanie: multizbiór wierszy + tolerancja numeryczna = czysta, testowalna funkcja.
- Złota prawda z ręcznie zweryfikowanego SQL na `marts.*` (guardrail-safe).
- Odmowa liczy się jako poprawna tylko, gdy jej oczekiwano.
- Model wstrzykiwany przez `build_pipeline(llm=...)` — łatwe testy z atrapami.
- API tylko czyta raport; liczenie jest offline.
