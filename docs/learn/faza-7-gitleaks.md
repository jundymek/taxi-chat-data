# Faza 7 — Skanowanie sekretów: gitleaks nad całą historią

Notatka do nauki (PL). Kod, komentarze i nazwy — po angielsku; ta notatka
tłumaczy „dlaczego”.

## Problem: usunięcie sekretu z pliku go nie usuwa

Git przechowuje **każdą wersję** każdego pliku. Jeśli w poniedziałek wrzucisz
klucz API do repo, a we wtorek go skasujesz i zacommitujesz — klucz dalej jest
w historii, dostępny przez `git show <stary-commit>`. Dla atakującego, który
sklonował repo, „usunięcie” nic nie znaczy.

Stąd kluczowa decyzja konfiguracyjna: skanujemy **całą historię**, nie tylko
zmiany w bieżącym PR:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0   # pełna historia; domyślnie jest shallow clone (1 commit)
```

`fetch-depth: 0` wyłącza *shallow clone*. Bez tego skaner zobaczyłby wierzchołek
gałęzi i przegapił wszystko, co starsze.

## Warstwy obrony (defense in depth)

Skaner to ostatnia linia, nie jedyna. W projekcie mamy trzy warstwy:

1. **Architektura** — uwierzytelniamy się przez ADC (Application Default
   Credentials), więc plików z kluczami po prostu *nie ma*. Najlepszy sekret to
   taki, który nie istnieje.
2. **`.gitignore`** — blokuje `*-key.json`, `*-sa.json`, `credentials.json`,
   `.env`. Zapobiega przypadkowemu dodaniu.
3. **gitleaks w CI** — wykrywa to, co mimo wszystko przeciekło.

## Allowlista: wąsko, nie szeroko

`.env.example` zawiera atrapy (`GCP_PROJECT_ID=your-project-id`), które mogą
uruchomić heurystykę „coś tu wygląda jak poświadczenie”. Wyjątek jest ścisły:

```toml
[extend]
useDefault = true          # rozszerzamy domyślne reguły, nie zastępujemy ich

[allowlist]
paths = ['''^\.env\.example$''']   # dokładnie jeden plik, kotwiczony regex
```

Zasada: **wyłączaj ścieżkę, nie regułę.** Globalne wyłączenie reguły
(`stripe-access-token`) uciszyłoby ją w całym repo na zawsze. Wyjątek na jeden
plik jest audytowalny — recenzent widzi dokładnie, co i dlaczego pominięto.

## Dwie pułapki, na które wpadliśmy

**1. Schemat konfiguracji.** Pierwotnie napisaliśmy:

```toml
[[allowlist.paths]]     # ŹLE dla gitleaks v8
path = '''...'''
```

gitleaks v8 odrzuca to przy starcie: `FTL Failed to load config ... expected
type 'string', got map`. Poprawnie jest `[allowlist]` z **tablicą** `paths`.
Lekcja: konfiguracja narzędzia to też kod — sprawdź, że w ogóle się ładuje.

**2. Sekret testowy, który nie jest sekretem.** Chcieliśmy udowodnić, że bramka
działa, podkładając fałszywy klucz. Użyliśmy `AKIAIOSFODNN7EXAMPLE` — i gitleaks
**nic nie wykrył**. Bo to publiczny placeholder z dokumentacji AWS, celowo
ignorowany przez reguły.

To najgroźniejszy rodzaj błędu: test „przechodzi”, sugerując że wszystko gra,
podczas gdy nie zweryfikował niczego. Dopiero wzorzec o realnym kształcie
(Stripe) dał `leaks found: 1` i dowód, że bramka faktycznie strzela.

**Reguła ogólna: bramka bezpieczeństwa, która nigdy nie zapaliła się na
czerwono, nie jest sprawdzona.** Zanim jej zaufasz — spróbuj ją złamać.

## Incydent: skaner złapał własnego autora

Najlepsza lekcja tej fazy. Naprawiając opis testu w dokumencie planu, wpisano
tam **literalny** klucz w kształcie Stripe. Efekt: przy pierwszym prawdziwym
uruchomieniu gitleaks zgłosił wyciek — w commicie, który *naprawiał test
gitleaksa*.

Trzy wnioski:
- Dokumentacja jest skanowana tak samo jak kod. Plik `.md` z przykładowym
  kluczem to dla skanera wyciek.
- Rozwiązanie: nie zapisuj wzorca dosłownie, składaj go w locie:
  `printf 'key = "%s"\n' "sk_live_$(printf '...')"`.
- Naprawa wymagała **przepisania historii** (`git filter-branch`), bo poprawienie
  bieżącego pliku nie rusza starych commitów.

## Przepisywanie historii — i pułapka „duchów”

Po `git filter-branch` skan **nadal** pokazywał wyciek. Powód: stary commit był
wciąż osiągalny przez dwie inne referencje:
- gałąź zapasową, którą zrobiliśmy przed operacją,
- `refs/original/`, którą `filter-branch` tworzy automatycznie.

Dopóki *jakakolwiek* referencja wskazuje na commit, obiekt żyje i skaner go widzi.
Trzeba było usunąć obie.

Uwaga praktyczna: przepisywanie historii jest bezpieczne, **dopóki gałąź nie jest
współdzielona**. Nasza nie była wypchnięta, więc nikt nie musiał robić
`git pull --rebase`. Na wypchniętej gałęzi zespołowej to poważna decyzja.

## Dlaczego uruchamiamy obraz, a nie `gitleaks-action`

Pierwotnie job używał `gitleaks/gitleaks-action@v2`. Problem: ta akcja wymaga
**płatnej licencji** dla repozytoriów innych niż publiczne repo osoby prywatnej.
To repo jest prywatne, więc job by padł — i to w sposób mylący, bo „czerwony
z powodu licencji” wygląda identycznie jak „czerwony, bo znalazł sekret”.

Zamiast tego wywołujemy oficjalny obraz w zwykłym kroku:

```yaml
- run: |
    docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.30.1 \
      detect --source=/repo --config=/repo/.gitleaks.toml --redact --verbose
```

Dwie dodatkowe korzyści:
- **Przypięta wersja** (`v8.30.1`, nie `:latest`) — nowe wydanie upstream nie
  zmieni po cichu zachowania bramki.
- Zewnętrzna akcja nie dostaje `GITHUB_TOKEN`. Uruchamianie skanera sekretów
  przez third-party akcję z tokenem zapisu to sprzeczność sama w sobie.

`--redact` sprawia, że znaleziony sekret nie trafia w całości do publicznych
logów CI — bo log builda też bywa czytany przez postronnych.

## Uprawnienia tokenu (`permissions`)

Każdy workflow dostaje automatyczny `GITHUB_TOKEN`. Bez jawnej deklaracji
obowiązuje domyślna konfiguracja repo — historycznie bywał to zapis do wszystkiego.
Job instalujący ~40 paczek z PyPI z tokenem zdolnym do pushowania to realne
ryzyko łańcucha dostaw.

```yaml
permissions:
  contents: read     # najmniejsze potrzebne uprawnienie
```

W tym repo domyślne uprawnienia i tak były `read` (sprawdziliśmy przez API), więc
realna ekspozycja była zerowa — ale jawny blok sprawia, że gwarancja nie zależy
od przełącznika w ustawieniach, który ktoś może kiedyś zmienić.

## Pojęcia do zapamiętania

- **Shallow clone** — płytki klon (domyślnie w CI); `fetch-depth: 0` pobiera całość.
- **Defense in depth** — kilka niezależnych warstw zamiast jednej „idealnej”.
- **Least privilege** — daj minimalne uprawnienia potrzebne do zadania.
- **Supply chain** — ryzyko płynące z zależności i zewnętrznych akcji, nie z Twojego kodu.
- **Osiągalność obiektu w gicie** — commit żyje, dopóki wskazuje na niego jakakolwiek referencja.
