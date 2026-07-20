# Faza 7 — CI: lint, testy i walidacja dbt bez chmury

Notatka do nauki (PL). Kod, komentarze i nazwy — po angielsku; ta notatka
tłumaczy „dlaczego”.

## Po co CI w projekcie, który i tak odpalam ręcznie

CI (Continuous Integration) to automat, który przy każdym pushu/PR odtwarza
weryfikację projektu **na czystej maszynie**. Wartość nie polega na tym, że
„coś się uruchamia”, tylko na tym, że sprawdza to, czego lokalnie nie widać:
czy projekt działa bez Twojego `.venv`, bez Twoich credentiali, bez plików,
które masz na dysku, a których nie ma w repo.

Dokładnie to nas tu złapało — patrz sekcja o dbt niżej.

## Ruff — jeden linter zamiast czterech

`ruff` zastępuje flake8 + isort + pyupgrade + część pylinta, i jest o rzędy
wielkości szybszy (napisany w Ruście). Konfiguracja siedzi w `pyproject.toml`:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Co znaczą te litery:
- **E** — pycodestyle: styl formalny (np. zbyt długa linia).
- **F** — pyflakes: realne błędy, np. nieużyty import, użycie niezdefiniowanej nazwy.
- **I** — isort: kolejność importów (stdlib → third-party → lokalne).
- **UP** — pyupgrade: przestarzałe konstrukcje, np. `datetime.timezone.utc` → `datetime.UTC`.
- **B** — bugbear: pułapki logiczne, np. `zip()` bez `strict=`.

Świadomie **nie** wybraliśmy `select = ["ALL"]`. Wąski zestaw to bramka na
poprawność, a nie migracja stylu — szerszy zestaw wygenerowałby setki zgłoszeń
i zamienił zadanie „dodaj CI” w przepisywanie całego repo.

## Dlaczego `ruff format` NIE jest w CI

`ruff check` szuka błędów; `ruff format` przeformatowuje kod (jak `black`).
Zmierzyliśmy: `ruff format` dotknąłby **33 z 44 plików**. To ogromny diff, który
nie naprawia ani jednego realnego błędu, a zaśmieciłby historię gita
(`git blame` na każdej linii pokazywałby „reformatowanie”, nie autora logiki).

Wniosek do zapamiętania: **formatowanie i lintowanie to dwie różne decyzje.**
Formatowanie można przyjąć później, jednym osobnym commitem.

## Ciekawy przypadek: `zip(..., strict=True)`

Bugbear zgłosił `zip()` bez `strict=`. Domyślnie `zip` **po cichu ucina** do
krótszej sekwencji:

```python
list(zip([1, 2, 3], ["a", "b"]))   # [(1,'a'), (2,'b')] — trójka zniknęła
```

W kodzie ewaluacji porównywaliśmy wiersze wyników SQL. Ciche ucięcie oznaczałoby
„porównałem tylko część i uznałem, że się zgadza” — czyli fałszywie zawyżony
wynik modelu. `strict=True` zamienia niewidzialny błąd w głośny `ValueError`.

To dobry przykład, że lint bywa czymś więcej niż kosmetyką.

## Trzy joby i zasada „CI bez sekretów”

Workflow (`.github/workflows/ci.yml`) ma joby uruchamiane **równolegle**, żeby
każda awaria była widoczna osobno: `lint`, `test`, `dbt` (+ `secrets`, opisany
w [faza-7-gitleaks.md](faza-7-gitleaks.md)).

Kluczowa decyzja: **CI nie dostaje żadnych danych dostępowych do GCP.**
Alternatywy, które odrzuciliśmy:
- klucz service-account w GitHub Secrets — sprzeczne z zasadą projektu (nie mamy
  plików kluczy, uwierzytelniamy się przez ADC),
- Workload Identity Federation (OIDC) — poprawne produkcyjnie, ale to spora
  konfiguracja po stronie GCP, nieproporcjonalna do projektu.

Dlatego zamiast `dbt test` (wymaga żywej hurtowni) CI uruchamia `dbt parse`,
który waliduje SQL modeli, powiązania `ref()`/`source()` i pliki YAML **bez
łączenia się z BigQuery**. `dbt test` dalej działa lokalnie i w Airflow.

## Pułapka: wersja Pythona dla dbt

Projekt stoi na Pythonie 3.14. Job `dbt` dostał jednak **3.12** i to nie jest
niekonsekwencja:

`dbt-bigquery` (pin `>=1.8,<2.0` rozwiązuje się dziś do **1.12.0**) deklaruje
w metadanych na PyPI wsparcie tylko do Pythona **3.13**. Uruchomienie go na 3.14
to proszenie się o czerwone CI z powodu narzędzia, a nie naszego kodu.

Zasada: **dbt jest narzędziem, nie naszym kodem.** Wersja Pythona dla narzędzia
ma pasować do środowiska, w którym to narzędzie faktycznie testowaliśmy — u nas
`dbt/Dockerfile` używa 3.12, więc CI też.

Sprawdziliśmy to empirycznie przed pushem: symulacja joba w czystym kontenerze
`python:3.12-slim`, bez credentiali i z pustym `target/` → `dbt deps` i
`dbt parse` kończą się kodem 0.

## `DBT_PROFILES_DIR` — jawnie zamiast „samo znajdzie”

dbt szuka `profiles.yml` domyślnie w `~/.dbt/`. Na Twoim laptopie działa też
fallback do katalogu projektu, ale na czystym runnerze `~/.dbt/` nie istnieje.
Nasz własny `dbt/Dockerfile` ustawia `ENV DBT_PROFILES_DIR` — czyli już wcześniej
nie ufaliśmy domyślnemu wyszukiwaniu. CI robi to samo jawnie.

Ogólna lekcja: **jeśli coś działa lokalnie „samo”, w CI ustaw to wprost.**
Lokalne środowisko jest pełne stanu, którego nie widzisz.

## Czego się nauczyliśmy o samym CI

Push na branch feature'owy **nic nie uruchomił** — bo wyzwalacz to
`push: branches: [master]` oraz `pull_request`. CI ruszyło dopiero przy
otwarciu PR. To zamierzone (nie marnujemy minut na każdy roboczy commit), ale
warto wiedzieć, kiedy realnie zobaczysz wynik.

## Pojęcia do zapamiętania

- **CI** — automatyczna weryfikacja na czystym środowisku przy każdej zmianie.
- **Job równoległy vs sekwencyjny** — równoległe joby dają szybszy i czytelniejszy
  feedback (widzisz wszystkie awarie naraz, nie pierwszą z brzegu).
- **`dbt parse` vs `dbt test`** — walidacja składni/grafu (offline) kontra
  odpytanie hurtowni (online).
- **Pin zależności** — `>=1.8,<2.0` to zakres, nie konkretna wersja; bez
  lockfile dwa środowiska mogą dostać różne wersje tego samego dnia.
