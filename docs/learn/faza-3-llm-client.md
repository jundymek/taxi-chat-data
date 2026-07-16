# Faza 3 — `llm_client.py`: klient HTTP do Ollamy

## Czym jest Ollama i po co nam ona?

Ollama to program, który uruchamia modele językowe (LLM) **lokalnie na Twoim
komputerze** i wystawia je przez proste HTTP API na `http://localhost:11434`.
Nie ma kluczy API, nie ma kosztów za token, dane nie wychodzą poza maszynę —
idealne do nauki i do projektu, gdzie model ma tłumaczyć polskie pytania na SQL.

Z punktu widzenia naszego kodu Ollama to po prostu serwer HTTP. Dlatego cały
"klient LLM" mieści się w ~50 liniach: budujemy JSON, robimy `requests.post`,
czytamy JSON z odpowiedzi. Zero frameworków — i o to chodzi. Warto zobaczyć,
że pod spodem LangChainów i SDK-ów zawsze siedzi taki właśnie request.

## Dwa endpointy: `/api/generate` vs `/api/embed`

Używamy dwóch różnych operacji:

1. **`POST /api/generate`** — generacja tekstu. Wysyłamy:
   ```json
   {"model": "gemma4:latest", "prompt": "...", "system": "...", "stream": false}
   ```
   - `prompt` — właściwe pytanie/zadanie,
   - `system` — instrukcja "kim jesteś" (np. "jesteś generatorem SQL"),
     ustawiana osobno, bo modele traktują ją z wyższym priorytetem niż prompt,
   - `stream: false` — **ważne**: domyślnie Ollama streamuje odpowiedź
     kawałek po kawałku (wiele linii JSON). Dla pipeline'u NL2SQL nie chcemy
     strumienia, tylko jedną kompletną odpowiedź w polu `response`.

2. **`POST /api/embed`** — embeddingi. Wysyłamy listę tekstów w polu `input`,
   dostajemy listę wektorów w polu `embeddings` (lista list floatów).

## Co to jest embedding i czemu robi go INNY model?

Embedding to **wektor liczb reprezentujący znaczenie tekstu**. Teksty o
podobnym znaczeniu ("ile kursów było w maju?" i "liczba przejazdów w maju")
dostają wektory leżące blisko siebie w przestrzeni. To fundament RAG:
w fazie 3 zaindeksujemy opisy tabel i przykładowe pary pytanie→SQL, a potem
dla nowego pytania znajdziemy najbliższe wektory — czyli najbardziej pasujący
kontekst do promptu.

Generacją zajmuje się `gemma4:latest`, ale embeddingi robi
`nomic-embed-text:latest`, bo:
- modele embeddingowe są **wyspecjalizowane**: trenowane tak, by odległość
  wektorów odzwierciedlała podobieństwo znaczeń (model generatywny tego nie
  gwarantuje),
- są **dużo mniejsze i szybsze** — embedding tysiąca dokumentów modelem 27B
  byłby absurdalnie drogi,
- wektory muszą być **spójne**: indeksowanie i wyszukiwanie musi używać tego
  samego modelu, więc `embed()` celowo ignoruje `self.model` i zawsze bierze
  `config.EMBEDDING_MODEL` — to świadoma decyzja kontraktowa, nie przeoczenie.

## Czemu opakowujemy błędy w domenowy `LLMError`?

Gdyby `requests.ConnectionError` poleciał z głębi `retriever.py` przez
LangGraph aż do CLI, użytkownik zobaczyłby traceback o gniazdach TCP.
Zamiast tego łapiemy wyjątki sieciowe i rzucamy własny `LLMError` z
**podpowiedzią po polsku**: "Uruchom `ollama serve`...". Zalety:

- **Warstwy wyżej nie znają `requests`** — pipeline łapie jeden typ wyjątku
  (`LLMError`) i nie obchodzi go, czy problem to DNS, timeout czy HTTP 500.
  Gdybyśmy kiedyś zamienili `requests` na `httpx`, zmienia się tylko ten plik.
- **Błąd jest akcjonowalny** — mówi użytkownikowi, co zrobić, zamiast co
  poszło nie tak w bibliotece.
- `raise ... from exc` zachowuje oryginalny wyjątek w `__cause__`, więc przy
  debugowaniu nic nie ginie.

Walidujemy też **kształt odpowiedzi**: jeśli w JSON-ie nie ma klucza
`response`/`embeddings`, rzucamy `LLMError` od razu, zamiast pozwolić, by
`KeyError` wybuchł gdzieś daleko od przyczyny.

## Czemu testy mockują `requests.post`?

W testach jednostkowych podmieniamy `requests.post` przez `monkeypatch` na
funkcję zwracającą przygotowany `FakeResponse`. Powody:

- **Determinizm** — prawdziwy LLM na to samo pytanie odpowiada różnie;
  test na "wygeneruj SQL" raz by przechodził, raz nie.
- **Szybkość** — 5 testów w 0.01 s zamiast sekund na inferencję.
- **Brak zależności środowiskowych** — testy przechodzą na CI i u każdego,
  kto nie ma uruchomionej Ollamy ani ściągniętych modeli.
- **Testujemy NASZ kod, nie Ollamę** — czy budujemy właściwy URL i payload
  (`stream: false`, właściwy model), czy poprawnie tłumaczymy błędy na
  `LLMError`. Słownik `captured` w testach przechwytuje wysłany payload
  i pozwala te kontrakty zweryfikować wprost.

Test ścieżki "Ollama leży" jest wręcz **niemożliwy** do napisania wiarygodnie
na żywym serwerze — mock (`raise requests.ConnectionError`) symuluje awarię
w jednej linii. Testy z prawdziwą Ollamą/BigQuery mają osobne miejsce:
`@pytest.mark.integration`, domyślnie wyłączone w `pytest.ini`.
