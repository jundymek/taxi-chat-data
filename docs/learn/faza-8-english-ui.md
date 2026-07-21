# Faza 8 — przejście na angielski UI (projekt portfolio)

## Po co

Projekt ma być wizytówką w portfolio, więc interfejs i komunikaty widoczne dla
użytkownika muszą być po angielsku. Notatki w `docs/learn/` **zostają po polsku** —
to materiał do nauki, nie część produktu.

## Czego się nauczyłem

### 1. „Przetłumaczenie UI" to nie tylko pliki `.tsx`

Pierwszy grep po `frontend/src` wyglądał na pełny obraz. Nie był. Polskie stringi
widoczne dla użytkownika siedziały w czterech warstwach:

| Warstwa | Przykład | Gdzie widać |
|---|---|---|
| Komponenty React | `"Zapytaj"`, `"SESJE"` | wprost w UI |
| Komunikaty guardrails (Python) | `"Dozwolone są wyłącznie zapytania SELECT"` | w karcie wyniku po odrzuceniu |
| Prompty do LLM-a | `"Answer in POLISH"` | w prozie odpowiedzi |
| Przykłady few-shot (RAG) | `"Ile było wszystkich przejazdów?"` | pośrednio — przez jakość SQL |

Gdybym przetłumaczył tylko pierwszą warstwę, aplikacja odpowiadałaby po polsku
na angielskie pytania — gorzej niż spójnie polski interfejs.

### 2. Sprzężenie stringów między frontendem a backendem

`StageTimeline.tsx` miał funkcję `cleanReason()`, która obcinała szum z komunikatu
BigQuery, dopasowując **dosłowny polski prefiks**:

```ts
const WRAPPER = "BigQuery odrzucił zapytanie:";   // <- musi się zgadzać z guardrails.py
if (!reason.startsWith(WRAPPER)) return reason;
```

Ten sam napis powstaje w `genai/guardrails.py`. Zmiana tylko po jednej stronie
nie wywala testów ani typów — funkcja po cichu przestaje czyścić komunikat i
użytkownik dostaje na ekranie surowy URL z Job ID. **Wniosek:** string dzielony
przez dwie usługi to ukryty kontrakt. Jeśli zostaje, zasługuje na komentarz
wskazujący drugą stronę.

### 3. Wymuszanie języka odpowiedzi vs dopasowanie do pytania

Pierwotnie pipeline miał zakodowane na sztywno:

```python
SUMMARY_SYSTEM = "... Answer in POLISH ..."
prompt = f"Question (Polish): {question}\n... Answer the question in Polish."
```

Zamiast przestawić to na „zawsze angielski", lepsze jest **dopasowanie do języka
pytania** — działa dla obu przypadków i nie wymusza sztucznego ograniczenia:

```python
SUMMARY_SYSTEM = (
    "... Reply in the SAME LANGUAGE as the user's question — if they ask in "
    "Polish, answer in Polish; if they ask in English, answer in English."
)
```

Ważne: sam system prompt **nie wystarczył**. Prompt użytkownika miał twarde
`"Question (Polish)"` i `"Answer the question in Polish."`, co nadpisywało
instrukcję systemową. Trzeba było zmienić oba miejsca.

Zastrzeżenie: to instrukcja dla modelu, nie deterministyczny przełącznik.
Mniejsze modele (`llama3.1`, `gemma`) potrafią zdryfować do angielskiego mimo
polskiego pytania.

### 4. Przykłady few-shot to nie są zwykłe dane

`genai/examples.yml` trafia do Chromy i jest dopasowywany **wektorowo** do pytania
użytkownika. Polskie przykłady + angielskie pytanie = słabe podobieństwo
semantyczne → retriever podsuwa gorsze przykłady → gorszy wygenerowany SQL.
Tłumaczenie ich nie było kosmetyką, tylko warunkiem działania RAG-u po angielsku.

### 5. Zielone testy potrafią być mylące

Po zmianie komunikatów guardrails backend dalej pokazywał 105/105. Powód: testy
asertowały na danych testowych, nie na komunikatach. Ale jeden test kryl martwą
asercję:

```python
assert "poprzednia próba" in prompt.lower() or "previous attempt" in prompt.lower()
```

Przechodził wyłącznie dzięki drugiemu członowi `or` — polska połowa nie
sprawdzała już niczego. **Wniosek:** „testy przechodzą" ≠ „testy nadal testują
to, co myślisz". Po zmianie stringów warto sprawdzić, czy asercje faktycznie
dotykają zmienionego kodu.

### 6. `<html lang>` — złapane dopiero na żywej stronie

Testy jednostkowe renderują komponenty, nie `index.html`, więc nikt nie zauważył,
że dokument nadal deklarował `lang="pl"` przy w pełni angielskim interfejsie.
Wyszło dopiero przy oglądaniu prawdziwej strony przez Playwright.

To realny błąd dostępności: czytnik ekranu przeczytałby angielski tekst z polską
wymową. **Wniosek:** zmiany językowe warto sprawdzić na uruchomionej aplikacji,
bo część rzeczy (atrybuty `<html>`, `<title>`, layout przy dłuższych napisach)
leży poza zasięgiem testów komponentów.

### 7. Czego celowo NIE ruszyłem

W `frontend/src/__tests__/chatClient.test.ts` został polski znak `"ó"`:

```ts
// "ó" = 0xC3 0xB3, dostarczane po jednym bajcie na odczyt (i flush na EOF).
expect(out).toBe("ó");
```

To test dekodowania wielobajtowego UTF-8 na granicy chunków SSE. Podmiana na
ASCII wyłączyłaby go po cichu — asercja dalej by przechodziła, ale nie
sprawdzałaby już niczego istotnego. Znak nie-ASCII **jest** tu przedmiotem testu.

## Co wyszło dopiero przy realnym użyciu

Po odpaleniu aplikacji pytanie „What was avarage tip in january 2023?" poleciało
trzy razy pod rząd na guardrails. Objawy wyglądały na jeden błąd, a były cztery
niezależne przyczyny:

| Objaw | Przyczyna |
|---|---|
| Polskie komunikaty guardrails w UI | proces API działał od 3 dni — serwował kod sprzed tłumaczenia |
| `cleanReason()` nie obcinało Job ID | front szukał `"BigQuery rejected the query:"`, backend słał polski prefiks |
| `Name tip not found inside t` | RAG widział 5 z 15 kolumn `fct_trips` |
| RAG nie podsunął dobrego przykładu | indeks Chroma był o dzień starszy niż przetłumaczone `examples.yml` |

### Lekcja 1: dokumentacja dbt jest kontekstem dla LLM-a, nie tylko dla ludzi

`genai/indexer.py` czyta `_marts__models.yml` i to **jest** schemat, który widzi
model. A ten plik dokumentował tylko kolumny mające testy dbt — czyli klucze i
relacje. Wszystkie miary (`tip_amount`, `fare_amount`, `total_amount`,
`trip_distance`…) nie miały testów, więc nikt ich nie opisał.

Efekt: model dostawał listę 5 kolumn, wśród których nie było żadnej, o którą
pytają użytkownicy. Do tego opis tabeli głosił `"Measures: fare, tip, tolls"` —
co czyta się jak lista kolumn i stąd wzięło się `t.tip`.

**Wniosek:** w projekcie z RAG-em nad warehousem „udokumentuj kolumnę" przestaje
być kwestią higieny, a staje się warunkiem poprawności. Kryterium „czy ta kolumna
ma test?" jest tu bez znaczenia — liczy się „czy ktoś o nią zapyta?".

### Lekcja 2: błąd potrafi się ukrywać za innym mechanizmem

Ta luka istniała **przed** tłumaczeniem, ale jej nie było widać: polskie przykłady
few-shot zawierały gotowe `AVG(f.tip_amount)`, więc model kopiował prawidłową
nazwę z przykładu zamiast czytać ją ze schematu. Dopiero gdy angielskie pytania
trafiły na indeks pełen polskich przykładów, podpórka zniknęła i luka wyszła.

Czyli RAG maskował braki w dokumentacji schematu. Zmiana języka nie stworzyła
błędu — odsłoniła go.

### Lekcja 3: po zmianie danych trzeba przebudować indeks

`data/chroma` to zmaterializowana kopia `examples.yml` i opisów dbt. Edycja
źródeł **nie** aktualizuje indeksu — trzeba wywołać `python -m genai.indexer`.
Porównanie dat plików to pierwsze, co warto sprawdzić, gdy RAG zwraca dziwne
wyniki:

```bash
stat -f '%Sm %N' data/chroma genai/examples.yml
```

### Lekcja 4: restartuj proces po zmianie kodu

`uvicorn --reload` przeładowuje zmiany tylko w procesie, który *już działa*.
Proces uruchomiony 3 dni wcześniej pamiętał stan sprzed tłumaczenia. Zanim
zacznie się debugować „dlaczego moja zmiana nie działa", warto sprawdzić, czy
proces w ogóle ją widzi:

```bash
lsof -ti:8000 | while read p; do ps -o pid,lstart -p $p | tail -1; done
```

## Efekt

- `pytest`: 105 passed
- `vitest`: 46 passed (9 plików)
- `ruff` i `tsc --noEmit`: czysto
