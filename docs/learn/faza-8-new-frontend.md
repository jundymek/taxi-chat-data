# Faza 8 — redesign frontu na „operations console" (notatka do nauki)

Notatka po polsku do przebudowy wyglądu chatu z kierunku **C1 „Linia M"** na
kierunek **1C „Operations console"**. Kod: `frontend/src/app/styles.css`,
`frontend/src/components/*`, `frontend/src/app/App.tsx`.

To notatka nie o „przemalowaniu na inne kolory", tylko o tym, **co się dzieje z
kodem, gdy zmienia się założenie projektowe** — i o dwóch błędach CSS, których
ani TypeScript, ani testy jednostkowe nie wykryły.

## 1. Skąd wziął się design i czym jest kierunek 1C

Design przyszedł jako projekt w Claude Design (plik `Kierunki.dc.html`) z trzema
wariantami. Wybraliśmy `1c`:

> **Operations console** — gęsty, statusowy warsztat; dla kogoś, kto siedzi w
> tym narzędziu godzinami i chce rzutem oka widzieć SQL, koszt skanu i świeżość
> danych.

Kluczowe słowo to **gęsty**. Poprzedni wygląd (C1) był „plakatowy": duża
typografia, żółta linia metra, dużo powietrza, jedna kolumna 620 px. 1C idzie w
przeciwną stronę — dwie kolumny, 12 px tekst, cienkie linie 1 px, monospace na
danych. To nie jest kwestia gustu, tylko **innego użytkownika**: C1 projektowano
pod „pokaż mi odpowiedź", 1C pod „siedzę tu 3 godziny i porównuję zapytania".

### Czego NIE przepisaliśmy

Warto zobaczyć, co przetrwało redesign bez zmian:

- `useChatStream` — cała logika strumienia SSE,
- `streamParser`, `chatClient` — parsowanie ramek,
- `nextStageLabel`, `cleanReason` — czyste funkcje etykiet,
- `columnLabel`, `formatScan` — czyste funkcje prezentacji danych.

To jest **nagroda za rozdzielenie logiki od prezentacji**. Zmiana całego języka
wizualnego dotknęła wyłącznie JSX-a i CSS-a. Gdyby `cleanReason` siedziało
wewnątrz komponentu razem z klasami Tailwinda, redesign oznaczałby przepisywanie
regexpów na parsowanie błędów BigQuery — czyli ryzyko regresji w miejscu
niezwiązanym z wyglądem.

## 2. Tokeny: dlaczego nie wpisujemy kolorów do komponentów

W `styles.css` cała paleta 1C siedzi w bloku `@theme` Tailwinda v4:

```css
@theme {
  --color-shell: #f4f5f7;   /* tło aplikacji */
  --color-panel: #ffffff;   /* karty */
  --color-hair: #e2e4e9;    /* domyślna kreska 1 px */
  --color-ink: #191c22;     /* tekst główny */
  --color-accent: #2e6be6;  /* SQL, słupki, linki */
  --color-ok: #1a7f4e;      /* etap zakończony */
  --color-err: #c2382e;     /* etap odrzucony */
}
```

Tailwind v4 generuje z tego automatycznie klasy `bg-shell`, `text-ink`,
`border-hair` itd. — nie trzeba pliku konfiguracyjnego.

**Dlaczego tak, a nie `bg-[#f4f5f7]` w komponencie?** Bo nazwa niesie *rolę*, a
nie *wartość*. `border-hair` mówi „to jest domyślna cienka kreska"; `#e2e4e9`
mówi tylko „jasnoszary". Gdy przyjdzie wariant ciemny albo korekta kontrastu,
zmienia się jedna linia w `@theme`, a nie 40 miejsc w JSX. To ta sama zasada co
stałe zamiast magic numbers w kodzie.

## 3. Pułapka: kolizja nazw `@keyframes` z Tailwindem

W CSS `@keyframes` żyją w **globalnej przestrzeni nazw** — nie ma tu żadnego
scope'owania per plik czy per komponent. Tailwind definiuje własną animację
`pulse` (używaną przez `animate-pulse`). Jeśli napiszemy swoje:

```css
@keyframes pulse { 50% { opacity: .3 } }   /* ⚠ nadpisuje wersję Tailwinda */
```

…to w zależności od kolejności ładowania jedna definicja **cicho** wygra z
drugą. Nic się nie wysypie, nic nie ostrzeże — po prostu któraś animacja zacznie
wyglądać inaczej. Dlatego nasza nazywa się `station-pulse`:

```css
.frame-row.run .glyph { animation: station-pulse 1.1s ease-in-out infinite }
@keyframes station-pulse { 50% { opacity: .3 } }
```

Ta sama zasada dotyczy nazw CSS custom properties i klas globalnych: cokolwiek
trafia do globalnej przestrzeni nazw, prefiksuj czymś swoim.

## 4. Fonty: `font-family` to nie nazwa paczki npm

1C używa **Geist** (UI) i **JetBrains Mono** (dane). Design linkuje je z Google
Fonts, ale my bundlujemy je lokalnie (`@fontsource/*`) — jeden request
cross-origin mniej i brak zależności od zewnętrznego CDN-u przy starcie.

Tu wpadka warta zapamiętania. Paczka nazywa się `@fontsource/geist-sans`, więc
naturalne (i błędne) założenie to:

```css
--font-sans: Geist, ui-sans-serif, sans-serif;   /* ⚠ nie działa */
```

Prawdziwa rodzina zadeklarowana w CSS paczki to `'Geist Sans'`. Efekt błędu jest
zdradliwy: **nic się nie psuje**. Przeglądarka nie znajduje rodziny `Geist`,
cicho spada na `ui-sans-serif` i strona wygląda „prawie dobrze". Weryfikacja:

```bash
grep -h "font-family" node_modules/@fontsource/geist-sans/400.css
#   font-family: 'Geist Sans';
```

**Zasada:** nazwę rodziny czytaj z CSS-a paczki, nigdy nie zgaduj z nazwy paczki.

### Ligatury w SQL

JetBrains Mono ma ligatury programistyczne — renderuje `>=` jako pojedynczy znak
`≥`, a `!=` jako `≠`. W edytorze to ładne, ale w konsoli, z której **kopiuje się
SQL do BigQuery**, to ryzyko: użytkownik widzi inny operator niż faktycznie jest
w tekście. Dlatego wyłączamy je tam, gdzie pokazujemy kod:

```css
code, kbd, pre, samp { font-variant-ligatures: none }
```

## 5. Dwa błędy, które wykryła dopiero przeglądarka

Najważniejsza część tej notatki. Testy (43) przechodziły, `tsc` przechodził,
build przechodził — a UI było zepsute. **CSS to język układu, a nie typów; jego
błędy widać dopiero, gdy coś się wyrenderuje.**

### 5.1 Słupek o szerokości 999757 px

W tabeli wyników rysujemy słupek proporcjonalny do wartości (`width: 56%`).
Pierwsza wersja miała na tabeli `min-w-max`, a na komórce słupka `w-full`:

```jsx
<table className="w-full min-w-max ...">   {/* ⚠ */}
  ...
  <td className="w-full">
    <span className="block h-2 bg-[#eef1f6]">      {/* tor */}
      <span style={{ width: "56%" }} />            {/* wypełnienie */}
```

Powstało **sprzężenie zwrotne układu**: `min-w-max` mówi „tabela ma być tak
szeroka, jak jej najszersza zawartość", a `w-full` w komórce mówi „bądź tak
szeroka jak tabela". Każde przejście algorytmu układu powiększało oba wymiary.
Pomiar przez Playwright:

```
"firstBarWidth": "999757px"
```

Na zrzucie ekranu **wszystkie** słupki były pełnej długości, więc Manhattan
(19,84) wyglądał identycznie jak Staten Island (11,02) — wykres pokazywał
nieprawdę. Naprawa to usunięcie `min-w-max` i oddanie nadmiarowej szerokości
jednej kolumnie:

```jsx
<table className="w-full ...">
<th className="w-full min-w-[120px] px-4" />   {/* kolumna słupków */}
```

Po poprawce: `514.578px` i proporcje zgodne z danymi.

### 5.2 Poziomy scroll na telefonie

Sidebar miał sztywne `w-[196px]`. Na ekranie 390 px zostawało za mało miejsca:

```
MOBILE {"overflow":true,"scrollWidth":422,"clientWidth":390}
```

422 > 390, czyli strona przewija się w bok — jeden z najbardziej irytujących
błędów mobilnych. Naprawa: poniżej breakpointu `sm` szyna staje się paskiem na
całą szerokość nad treścią, a kolumną dopiero od `sm` w górę.

```jsx
// Sidebar
<aside className="w-full border-b sm:w-[196px] sm:border-b-0 sm:border-r">
// App — kierunek flexa musi się zmienić razem z tym
<div className="flex min-h-screen flex-col sm:flex-row">
```

Zwróć uwagę, że **obie** zmiany są konieczne. Sam `w-full` na `<aside>` nic by
nie dał, dopóki rodzic układa dzieci w wierszu.

### Wniosek metodyczny

Testy jednostkowe sprawdzają **logikę i treść** (czy jest tekst, czy funkcja
liczy dobrze). Nie sprawdzają **geometrii**. Dlatego przy zmianach wyglądu
mierzymy realny DOM w przeglądarce:

```js
const geo = await page.evaluate(() => ({
  sidebarWidth: document.querySelector("aside").getBoundingClientRect().width,
  firstBarWidth: getComputedStyle(bar).width,
  horizontalOverflow:
    document.documentElement.scrollWidth > document.documentElement.clientWidth,
}));
```

Liczby > zrzut ekranu > „wygląda ok". Zrzut pokazał *że* słupki są złe; pomiar
`999757px` powiedział *dlaczego*. Po weryfikacji usuwamy `playwright` z
`devDependencies` — to narzędzie do jednorazowego sprawdzenia, nie zależność
projektu.

## 6. Uczciwość UI: czego świadomie nie zbudowaliśmy

Design 1C pokazuje dwie rzeczy, których **nie** przenieśliśmy 1:1, i to jest
decyzja projektowa, nie zaniedbanie.

**Pigułka świeżości danych.** W mockupie widnieje `yellow_trips · 26h stale` i
żółty banner ostrzegawczy. Sprawdziliśmy backend: `GET /health` zwraca
*dostępność zależności* (`ollama`/`bigquery`/`chroma_index` = ok/down), a **nie
opóźnienie ładowania tabeli**. To dwie różne informacje i jednej nie da się
wyliczyć z drugiej. Wpisanie „26h" na sztywno dałoby UI, które **kłamie o stanie
danych** — gorsze niż brak tej informacji. Pigułka pokazuje więc to, co API
naprawdę wie, w wizualnym języku 1C. Prawdziwa świeżość wymaga osobnego
endpointu (np. `MAX(pickup_date)` vs `CURRENT_DATE()`) — to zadanie na później.

**Zakładka „Data health" w nawigacji.** Mockup ma nawigację `Ask` / `Data
health`, co sugeruje dwa ekrany. Aplikacja ma jeden. Dodanie martwej zakładki,
która nigdzie nie prowadzi, to **fałszywa kontrolka** — użytkownik klika i nic
się nie dzieje. Sygnał zdrowia został tam, gdzie jest żywy: w pigułce.

Analogicznie `SESJE`: w designie to statyczna lista przykładów. U nas to
**prawdziwe pytania zadane w tej karcie przeglądarki**, trzymane w pamięci
Reacta. Nie ma endpointu historii, więc kliknięcie sesji **wypełnia pole
pytania**, a nie „przywraca wynik" — i tak to opisujemy w kodzie. Pusty stan
mówi wprost: „Zadane pytania pojawią się tutaj".

> **Zasada:** lepiej pokazać mniej i prawdziwie niż odtworzyć mockup co do
> piksela kosztem informacji, która wprowadza w błąd. Mockup jest propozycją
> wyglądu, nie kontraktem na dane, których nie masz.

## 7. `useEffect`: kluczem jest *zdarzenie*, nie *dana*

Kliknięcie sesji ma wypełnić pole pytania. Podejście pierwsze:

```jsx
useEffect(() => { setQuestion(preset) }, [preset]);   // ⚠ preset: string
```

Błąd: użytkownik klika sesję, **edytuje tekst w polu**, po czym klika tę samą
sesję ponownie — `preset` (string) się nie zmienił, efekt nie wystrzeli, pole
zostaje z edytowanym tekstem. Podejście drugie, `preset = { id, question }` z
zależnością `[preset.id]`, ma **dokładnie ten sam błąd**: id tej samej sesji też
się nie zmienia.

To była realna pluskwa w tym zadaniu — i warto zobaczyć, *jak* wyszła. Nie
znalazł jej ani `tsc`, ani code review, tylko test napisany po to, żeby
**sprawdzić zdanie, które napisałem w tej notatce**:

```jsx
await ask("Ile kursów wczoraj?");
await userEvent.clear(field);
await userEvent.type(field, "zmienione");
await userEvent.click(screen.getByRole("button", { name: "Ile kursów wczoraj?" }));
expect(field).toHaveValue("Ile kursów wczoraj?");   // ← czerwony
```

Sedno: `useEffect` reaguje na **zmianę wartości**, a my chcemy reagować na
**zdarzenie** („użytkownik kliknął"). Kliknięcie tej samej pozycji drugi raz to
nowe zdarzenie, ale ta sama wartość. Rozwiązanie — licznik kliknięć jako
tożsamość *wyboru*, nie *sesji*:

```jsx
// App
const [pickCount, setPickCount] = useState(0);
const pick = (session) => { setActive(session); setPickCount(n => n + 1) };
<QuestionForm preset={active ? { id: pickCount, question: active.question } : undefined} />
```

Ogólna zasada: jeśli efekt ma odpalać przy każdym powtórzeniu akcji, zależnością
musi być coś, co **rośnie z każdą akcją** (licznik, timestamp), a nie dane, które
przy powtórzeniu są identyczne.

## 8. Kontrast: mockup nie jest audytem dostępności

Design 1C używa `#9aa1ad` na jasnoszare eyebrowsy, nagłówki tabeli, placeholder
i podsumowanie wierszy. Wygląda elegancko — i **nie spełnia WCAG AA**:

```
#9aa1ad na #ffffff → 2.60:1   (próg AA dla zwykłego tekstu: 4.5:1)
#9aa1ad na #f8f9fb → 2.47:1
```

To nie jest błąd projektanta mockupu — mockup pokazuje *kierunek wizualny*, a
nie gwarantuje dostępności. **Sprawdzenie kontrastu należy do implementacji.**

Zamiast zgadywać „chyba za jasne", policzyliśmy kontrast wszystkich 14 par
kolor/tło w palecie. Jedyną wadliwą był `faint`. Dobraliśmy najjaśniejszy kolor
na tej samej osi barwy, który zdaje AA na wszystkich trzech tłach:

```
#687182 → panel 4.91 · subtle 4.67 · shell 4.51
```

Kluczowe: **nie skoczyliśmy od razu do `--color-muted`**. Gdyby `faint` zrównał
się z `muted`, zniknąłby jeden z trzech stopni hierarchii tekstu i 1C straciłby
część swojej gęstości. Naprawa dostępności nie musi kasować projektu — trzeba
tylko poszukać najmniejszej wystarczającej zmiany.

### Pułapka: `opacity` na stanie `disabled`

Wyłączony przycisk miał `disabled:opacity-40`. Biały tekst na prawie czarnym
tle, wyblakły do 40%, daje ~1.5:1 — etykieta „Zapytaj" jest wtedy praktycznie
niewidoczna, **dokładnie w momencie, gdy użytkownik czeka na odpowiedź i patrzy
na przycisk**. `opacity` przygasza tekst *i tło naraz*, więc nigdy nie wiadomo,
jaki kontrast z tego wyjdzie. Rozwiązanie: jawna para kolorów.

```jsx
disabled:bg-hair-soft disabled:text-muted   /* 4.83:1 */
```

**Zasada:** stany trwałe (`disabled`, `readonly`) opisuj kolorami, nie
przezroczystością. `opacity` zostaw animacjom, gdzie stan jest przejściowy.

### Uwaga o narzędziach

Panel Accessibility w DevTools pokazał dla przycisku `1.49` — ale mierzył go w
stanie **wyłączonym** (z `opacity`). Ten sam przycisk aktywny to 17:1. Zanim
uznasz kontrast za zepsuty, sprawdź, **który stan** narzędzie właśnie mierzy.

## 9. Dwie pluskwy, które ujawniły dopiero prawdziwe dane

Po podłączeniu API + BigQuery + Ollama i zadaniu realnego pytania wyszły rzeczy,
których nie pokazały ani testy, ani dane przygotowane do zrzutów ekranu.

### 9.1 Słupek przy wyniku jednowierszowym

Pytanie „ile kursów w styczniu 2023?" zwraca **jeden wiersz**. Słupek skalowany
do maksimum kolumny miał wtedy zawsze 100% szerokości — pas koloru przez pół
karty, który **udaje wykres, nie niosąc żadnej informacji** (jedna wartość nie
ma się do czego porównać).

```js
if (rows.length < 2) return null;   // mniej niż dwa wiersze → brak słupków
```

Ogólniejsza lekcja: wizualizacja porównawcza (słupki, udziały, rankingi) ma sens
dopiero przy **co najmniej dwóch punktach**. Przy jednym pokaż samą liczbę.

### 9.2 `cleanReason` i nowe linie — dlaczego regexp „działał" w testach

Na żywym odrzuceniu z BigQuery w UI został śmieć, który ta funkcja miała
usuwać: `Location: None Job ID: e852ee68-…`. Ale uruchomiona w izolacji na tym
samym tekście — działała. Różnica: **prawdziwy komunikat miał znaki nowej
linii**, bo `google-cloud` renderuje `BadRequest` wielolinijkowo.

```js
body.replace(/\s*Job ID:.*$/i, "")    // ⚠ `.` nie łapie \n, `$` = koniec linii
body.replace(/\s*Job ID:.*$/is, "")   // ✓ flaga `s` (dotAll)
```

Wszystkie dotychczasowe testy `cleanReason` używały **jednolinijkowych**
komunikatów — dlatego luka przetrwała code review i 45 zielonych testów.

> **Zasada:** przy parsowaniu tekstu z zewnętrznego systemu testuj też wariant
> wielolinijkowy. `.` i `$` w JS domyślnie zatrzymują się na `\n`, a komunikaty
> błędów bibliotek chmurowych bywają wielolinijkowe częściej, niż się wydaje.

To najlepszy w tym zadaniu argument za uruchamianiem aplikacji na prawdziwych
danych: dane testowe piszemy **my**, więc mimowolnie omijamy w nich przypadki,
o których nie pomyśleliśmy.

## 10. Zawijanie SQL zamiast przewijania

Pierwsza wersja bloku SQL miała `overflow-x-auto`. Zgodne z zasadą „szerokie
treści przewijaj wewnątrz kontenera, nie rozpychaj strony" — ale **złe dla tego
konkretnego zastosowania**. To konsola, w której SQL się *czyta i kopiuje*;
poziomy pasek przewijania ukrywa końcówkę każdego dłuższego zapytania i zmusza
do przewijania w bok przy każdej linii.

```jsx
<pre className="whitespace-pre-wrap wrap-break-word ...">
```

`whitespace-pre-wrap` zachowuje własne podziały linii i wcięcia modelu, a
dodatkowo zawija to, co się nie mieści. Tabela wyników **nadal** przewija się w
poziomie — tam kolumn może być dowolnie wiele i zawijanie rozbiłoby siatkę.

Wniosek: „przewijać czy zawijać" to nie jest reguła globalna, tylko decyzja per
typ treści. Kod do czytania → zawijaj. Tabela → przewijaj.

## 11. Co sprawdzić po zmianach w wyglądzie

```bash
cd frontend
pnpm test     # 43 testy — logika, treść, dostępność
pnpm build    # tsc + vite: typy i bundling
pnpm lint     # oxlint
```

Plus pomiar w przeglądarce przy `pnpm dev` (port 3002), jeśli zmieniałeś układ:
szerokości, `scrollWidth` vs `clientWidth`, kolory z `getComputedStyle`.

## Podsumowanie

| Temat | Wniosek |
|---|---|
| Redesign | Czyste funkcje + rozdzielenie logiki od prezentacji = zmiana wyglądu nie dotyka logiki |
| Tokeny | Nazwa niesie rolę (`border-hair`), nie wartość (`#e2e4e9`) |
| `@keyframes` | Globalna przestrzeń nazw — prefiksuj (`station-pulse`, nie `pulse`) |
| Fonty | `font-family` czytaj z CSS-a paczki; zła nazwa = cichy fallback |
| Ligatury | Wyłącz w blokach kodu — `≥` to nie to samo co `>=` przy kopiowaniu |
| Układ | `min-w-max` + `w-full` w tabeli = sprzężenie zwrotne szerokości |
| Mobile | Sztywna szerokość sidebara → poziomy scroll; zmień też kierunek flexa |
| `useEffect` | Reaguje na zmianę wartości; na *powtarzalne zdarzenie* potrzeba licznika |
| Weryfikacja | Testy nie widzą geometrii — mierz DOM w przeglądarce |
| Kontrast | Mockup nie gwarantuje WCAG — policz wszystkie pary kolor/tło sam |
| `opacity` | Nie na stany trwałe (`disabled`) — przygasza tekst i tło naraz |
| Regexpy | `.` i `$` stają na `\n`; testuj warianty wielolinijkowe (flaga `s`) |
| Wykresy | Słupki mają sens od 2 punktów; przy jednym pokaż samą liczbę |
| Zawijać czy przewijać | Decyzja per typ treści: kod → zawijaj, tabela → przewijaj |
| Prawdziwe dane | Dane testowe piszemy my, więc omijają przypadki, o których nie pomyśleliśmy |
| Uczciwość | Nie odtwarzaj z mockupu danych, których backend nie ma |
