# Faza 5 / Task 1 — FastAPI + SSE (notatka do nauki)

Notatka po polsku do warstwy API: jak wystawić strumień etapów pipeline'u
GenAI przez **Server-Sent Events (SSE)** w FastAPI, nie dotykając grafu
LangGraph. Kod: `api/main.py`, kontrakt ramek: `api/schemas.py`.

## 1. Czym jest SSE i czym różni się od WebSocketów

**SSE** to jednokierunkowy strumień serwer → przeglądarka po zwykłym HTTP.
Serwer trzyma odpowiedź otwartą i dopisuje kolejne „zdarzenia" w prostym
formacie tekstowym:

```
event: stage
data: {"stage":"validate","ok":true}

```

Każde zdarzenie kończy się **pustą linią** (`\n\n`). To wszystko — żadnego
handshake'u, żadnego własnego protokołu ramek.

| | SSE | WebSocket |
|---|---|---|
| Kierunek | tylko serwer → klient | dwukierunkowy |
| Protokół | zwykły HTTP (`text/event-stream`) | osobny upgrade `ws://` |
| Reconnect | wbudowany w `EventSource` | trzeba samemu |
| Nasz przypadek | idealny — tylko *pushujemy* etapy | przerost formy |

Chcemy tylko wypychać postęp (retrieve → generate_sql → …), więc SSE wystarcza
i jest tańsze w utrzymaniu. **Uwaga:** natywny `EventSource` w przeglądarce
robi tylko `GET`. My wysyłamy pytanie `POST`-em, więc front NIE używa
`EventSource`, tylko `fetch` + `ReadableStream` (to strona bob-a / task 2).

## 2. `StreamingResponse` z generatorem

W FastAPI strumień to `StreamingResponse` owijający **generator bajtów**:

```python
@app.post("/chat")
def chat(request: ChatRequest):
    return StreamingResponse(
        stream_chat(_get_pipeline(), request.question),
        media_type="text/event-stream",
    )
```

`stream_chat` to zwykły generator (`yield sse(frame)`). FastAPI konsumuje go
leniwie — każdy `yield` leci do klienta od razu, a nie dopiero po zebraniu
całości. Dzięki temu użytkownik widzi „Guardraile OK" zanim BigQuery w ogóle
ruszy.

## 3. Skąd biorą się zdarzenia — LangGraph `stream_mode="updates"`

Pipeline z Fazy 3 to skompilowany graf LangGraph. Zamiast `invoke()` (jeden
wynik na końcu) wołamy `stream(..., stream_mode="updates")`, który po każdym
**węźle** oddaje słownik `{nazwa_węzła: łatka_stanu}`:

```python
for update in pipeline.stream({"question": q}, stream_mode="updates"):
    for node, patch in update.items():
        state.update(patch or {})          # akumulujemy pełny stan
        for frame in _frames_for(node, state):
            yield sse(frame)
```

Adapter **tylko mapuje** te aktualizacje na ramki SSE — nie zmienia grafu,
nie dokłada logiki biznesowej. To ważna zasada: `genai/` zostaje nietknięte,
API jest cienką warstwą tłumaczącą.

## 4. Semantyka ramek (to jest kontrakt z frontem)

- **Ramka = węzeł SIĘ ZAKOŃCZYŁ** (a nie „zaczął"). Niesie stan po węźle.
- Kolejność happy path:
  `retrieve → generate_sql → validate → execute → summarize → done`.
- **`summarize` emitujemy zaraz po `execute`** — znaczy „piszę teraz
  odpowiedź". Faktyczne zakończenie węzła `summarize`/`refuse` reprezentuje
  ramka terminalna `done` (patrz `_frames_for` — dla `execute` zwraca DWIE
  ramki, dla `summarize`/`refuse` żadnej).
- `generate_sql` niesie `attempt`; `validate` niesie `ok` (+ `reason` gdy
  `ok:false`). Przy retry są DWA `validate` (najpierw `ok:false`+powód, potem
  `ok:true`) i rosnący `attempt`.
- **Dokładnie JEDNA ramka terminalna** na żądanie: `done` (z pełnym `Result`)
  albo `error` (z `message`). Nigdy oba, nigdy zero.

## 5. Odmowa guardraili to `done`, a NIE `error`

Kluczowa decyzja: kiedy guardrail odrzuci SQL (np. „Tylko SELECT."), to jest
**poprawna, oczekiwana** odpowiedź produktu — nie awaria. Więc kończymy
ramką `done` z `result.refused = true` i `result.reason` (powód po polsku),
a `rows = []`. `error` rezerwujemy WYŁĄCZNIE na awarie infrastruktury
(Ollama/BigQuery padły w trakcie) — łapane jako `LLMError`/`Exception` i
zamieniane na jedną ramkę `error`. Front rysuje odmowę jako kartę wyniku,
a `error` jako czerwony baner — stąd rozróżnienie ma znaczenie.

## 6. `create_app(factory)` i leniwe budowanie pipeline'u

`create_app(pipeline_factory=None)` to fabryka aplikacji. W testach wstrzykujemy
**atrapę** (`FakePipeline`), która oddaje z góry ustawione aktualizacje — zero
Ollamy, zero BigQuery. W produkcji `factory=None` → leniwie `build_pipeline()`.

Ważny szczegół: pipeline budujemy **przy pierwszym żądaniu** (memoizacja na
`app.state.pipeline`), a nie przy imporcie modułu i nie w `@app.on_event(
"startup")`. Dlaczego nie startup? Bo `TestClient(app)` **bez** `with` nie
odpala cyklu życia (lifespan) Starlette — startup by się nie wykonał i
`app.state.pipeline` byłby pusty. Leniwe budowanie „na pierwszy strzał" działa
i w testach, i pod uvicornem, i nie płaci kosztu budowy przy `import`.

## 7. Testowanie strumienia przez `TestClient.stream`

`TestClient` (oparty na httpx) czyta SSE tak:

```python
with client.stream("POST", "/chat", json={"question": q}) as resp:
    body = b"".join(resp.iter_bytes()).decode()
frames = [json.loads(p.split("data: ", 1)[1])
          for p in body.split("\n\n") if p.startswith("event: stage")]
```

Dzielimy po `\n\n` (granica zdarzeń), bierzemy linię `data:`, parsujemy JSON.
Cały test jest **offline** — atrapa pipeline'u + (dla `/health`) podmienione
sondy `_check_ollama/_check_bigquery/_check_chroma` przez `monkeypatch`. To
pozwala sprawdzić kolejność ramek, retry, odmowę i błąd bez żadnej usługi.

## Do zapamiętania

1. SSE = jednokierunkowy push po HTTP; do POST-a na froncie idzie `fetch`, nie
   `EventSource`.
2. `StreamingResponse(generator)` streamuje leniwie — `yield` = natychmiast do
   klienta.
3. `stream_mode="updates"` daje stan po każdym węźle; adapter tylko MAPUJE.
4. Ramka = węzeł zakończony; dokładnie jedna ramka terminalna.
5. Odmowa = `done{refused:true}`, awaria = `error`. Nie mieszać.
6. Buduj pipeline leniwie (na pierwsze żądanie), nie w `on_event("startup")` —
   `TestClient` bez `with` nie odpala lifespanu.
