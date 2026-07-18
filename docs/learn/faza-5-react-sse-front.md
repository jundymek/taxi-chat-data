# Faza 5 — React + SSE: strumieniowy front chatu (notatka do nauki)

Notatka towarzyszy zadaniu `faza-5-task-2` (ekran C1 „Linia M"). Pokazuje, jak
czytać strumień Server-Sent Events w Reakcie, oddzielić logikę od prezentacji i
przetestować strumień bez żywego serwera.

## 1. Dlaczego `fetch` + `ReadableStream`, a nie `EventSource`

Przeglądarkowe `EventSource` (natywne API do SSE) obsługuje **wyłącznie GET** i
nie pozwala ustawić ciała żądania. Nasze `/chat` jest `POST` z JSON-em
(`{"question": ...}`), więc `EventSource` odpada. Zamiast tego:

```ts
const response = await fetch("/chat", { method: "POST", body: JSON.stringify(...), signal });
const reader = response.body.getReader();      // ReadableStream<Uint8Array>
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  yield decoder.decode(value, { stream: true }); // fragment tekstu SSE
}
```

`response.body` to strumień bajtów. `TextDecoder` z opcją `{ stream: true }`
poprawnie skleja znaki wielobajtowe (UTF-8, np. polskie znaki) na granicy
chunków. Funkcja jest **async generatorem** — konsument robi `for await`.

## 2. Czysty parser SSE (bufor + granica `\n\n`)

Sieć nie gwarantuje, że jeden `read()` = jedno zdarzenie SSE. Zdarzenie może
przyjść w kawałkach albo kilka naraz. Dlatego parser trzyma **bufor** i wycina
kompletne zdarzenia na granicy pustej linii (`\n\n`):

```ts
export function createFrameParser(): (chunk: string) => Frame[] {
  let buffer = "";
  return (chunk) => {
    buffer += chunk;
    const frames: Frame[] = [];
    let b;
    while ((b = buffer.indexOf("\n\n")) >= 0) {
      const rawEvent = buffer.slice(0, b);
      buffer = buffer.slice(b + 2);
      const data = rawEvent.split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6)).join("");
      if (data) frames.push(JSON.parse(data) as Frame);
    }
    return frames;
  };
}
```

Kluczowe cechy:
- **Czystość względem I/O** — parser nie wie nic o sieci. Dostaje tekst, zwraca
  ramki. Dzięki temu testuje się go trywialnie (podajesz stringi).
- Czyta **tylko** linie `data:`; linie komentarza/keep-alive (`: ping`) są
  ignorowane (nie mają `data:`), więc nie psują parsowania.
- Częściowy chunk (`{"stage":"exe`) zostaje w buforze do czasu terminatora.

## 3. Podział logika / prezentacja

Konwencja „senior": **cała logika w hooku, komponenty bez logiki**.

- `useChatStream` jest właścicielem cyklu życia żądania: trzyma stan
  (`frames`, `result`, `error`, `running`), odpala strumień, mapuje ramki na
  stan. Rozróżnia trzy typy ramek:
  - `done` → ustawia `result` (to również **odmowa guardraili**: `done` z
    `result.refused === true`, NIE `error`);
  - `error` → ustawia `error` (awaria infrastruktury, np. Ollama down);
  - pozostałe → dokłada do `frames` (żywa oś czasu etapów).
- Komponenty (`StageTimeline`, `QuestionForm`, `ResultCard`, `HealthBar`) to
  czyste funkcje: props wchodzą, JSX wychodzi. Zero `useEffect`/`fetch` w
  środku. Łatwo je renderować w testach i podmieniać wygląd.

Terminalna ramka jest dokładnie jedna na żądanie (`done` XOR `error`) — kontrakt
ustalony z agentem API (faza-5-task-1) w intent-sync PRZED kodowaniem.

## 4. `AbortController` przy ponownym pytaniu

Gdy użytkownik zada nowe pytanie, poprzedni strumień trzeba przerwać, żeby jego
ramki nie „dopisywały się" do nowej odpowiedzi:

```ts
abortRef.current?.abort();               // ubij poprzedni
const controller = new AbortController();
abortRef.current = controller;
// ...streamChat(question, controller.signal)
catch (exc) { if (!controller.signal.aborted) setError(...); } // abort ≠ błąd
```

Przerwanie rzuca wyjątek w `fetch`/`read`, ale to **nie jest błąd aplikacyjny** —
sprawdzamy `signal.aborted` i wtedy nie ustawiamy `error`.

## 5. Testowanie strumienia w vitest bez serwera

Nie potrzebujemy żywego API. Budujemy sztuczny `Response` z `ReadableStream`,
który wypycha zakodowane zdarzenia SSE, i podmieniamy `fetch`:

```ts
function sseResponse(...events: string[]) {
  const body = new ReadableStream({
    start(c) { for (const e of events) c.enqueue(new TextEncoder().encode(e)); c.close(); },
  });
  return new Response(body, { status: 200 });
}
vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse(EV(...), EV(...))));
```

Hook renderujemy przez `renderHook`, wołamy `ask()` w `act`, a asercje czekają
przez `waitFor`, aż stan się ustabilizuje. Parser i komponenty testujemy wprost
(stringi / propsy). Razem: 10 testów (parser 4, hook 2, StageTimeline 2,
ResultCard 2) — zielone bez dotykania sieci, Ollamy czy BigQuery.

## 6. Stack (uwaga praktyczna)

React 19 + Vite 8 + Vitest 4 + Tailwind v4 (`@tailwindcss/vite`, konfiguracja
CSS-first przez `@theme`), pnpm. Oś czasu metra (żółta linia trasy, kropki
stacji, kropkowany lider) zostaje w małej warstwie **custom CSS** — pseudo-
elementy `::before` nie mapują się czysto na klasy utility, a wierność
zatwierdzonemu mockupowi C1 jest tu wymogiem (AC#2).
