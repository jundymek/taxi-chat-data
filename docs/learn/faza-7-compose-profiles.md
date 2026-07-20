# Faza 7 — Docker Compose: profile i granica host/kontener

Notatka do nauki (PL). Kod, komentarze i nazwy — po angielsku; ta notatka
tłumaczy „dlaczego”.

## Problem: dwa pliki compose i rozjeżdżająca się prawda

Mieliśmy `docker-compose.yml` (samo dbt) i `docker-compose.airflow.yml` (Airflow
+ Postgres). Dwa pliki to dwa miejsca, w których trzeba pamiętać o tej samej
zmianie — i dwa zestawy komend w dokumentacji, które łatwo rozjeżdżają się
z rzeczywistością.

Docelowo chcemy jednego pliku, ale bez efektu ubocznego: `docker compose up`
nie może nagle startować Airflow, Postgresa i API naraz, gdy potrzebujesz tylko
jednorazowego `dbt build`.

## Profile — rozwiązanie

Każda usługa dostaje etykietę:

```yaml
services:
  api:
    profiles: [api]
  airflow:
    profiles: [airflow]
```

Usługa z `profiles:` **nie startuje**, dopóki nie wskażesz jej profilu:

```bash
docker compose --profile api up          # tylko API
docker compose --profile airflow up -d   # Airflow + Postgres
docker compose --profile airflow --profile api up   # oba
```

Efekt uboczny wart zapamiętania: samo `docker compose up` nie uruchamia **nic**.
To celowe — wybór jest świadomy, nie przypadkowy.

## Dlaczego Ollama zostaje na hoście

Kuszące byłoby wrzucić wszystko do compose'a („jedna komenda uruchamia projekt”).
Świadomie tego nie zrobiliśmy:

- Kontener na macOS **nie ma dostępu do GPU**. Model chodziłby na CPU, czyli
  wielokrotnie wolniej.
- Modele (`gemma4`, `llama3.1:8b`, `nomic-embed-text`) to ~10 GB, które masz już
  pobrane na hoście. Kontener ściągnąłby je drugi raz.

Zasada ogólna: **konteneryzuj to, co zyskuje na izolacji, nie wszystko, co się da.**
Ollama jest usługą lokalną o dużym stanie — trzymanie jej na hoście jest tańsze
i szybsze.

## `host.docker.internal` — jak kontener widzi hosta

Wewnątrz kontenera `localhost` oznacza **sam kontener**, nie Twój laptop. Żeby
sięgnąć do usługi na hoście, Docker udostępnia specjalną nazwę:

```yaml
environment:
  OLLAMA_BASE_URL: http://host.docker.internal:11434
extra_hosts:
  - "host.docker.internal:host-gateway"
```

`extra_hosts` jest zbędne na macOS (Docker Desktop dodaje tę nazwę sam), ale
konieczne na Linuksie. Zostawiamy je dla przenośności.

## Najważniejsza lekcja: martwa konfiguracja

To był realny błąd, wykryty dopiero przy uruchomieniu. W compose ustawiliśmy
`OLLAMA_HOST`, ale kod w `genai/config.py` miał:

```python
OLLAMA_BASE_URL = "http://localhost:11434"   # wartość na sztywno
```

Kod **nigdy nie czytał żadnej zmiennej środowiskowej**. Zmienna w compose była
dekoracją: wyglądała sensownie w pliku, nie robiła nic. W kontenerze
`localhost:11434` wskazywał na pusty kontener → `/health` zgłaszał `ollama: down`.

Poprawka:

```python
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
```

Wzorzec do zapamiętania: **zmienna środowiskowa z sensownym domyślnym**.
Natywny dev-loop działa jak wcześniej (fallback na `localhost`), a kontener
dostaje właściwy adres. Nazwa zmiennej w compose musi się **dokładnie** zgadzać
z tą, którą czyta kod — `OLLAMA_HOST` ≠ `OLLAMA_BASE_URL`.

Diagnostyczna wskazówka: jeśli ustawiasz zmienną i „nic się nie zmienia”,
sprawdź najpierw, czy cokolwiek ją w ogóle odczytuje (`grep`).

## Wolumeny: co montować i w jakim trybie

```yaml
volumes:
  - ~/.config/gcloud:/root/.config/gcloud:ro   # poświadczenia — tylko do odczytu
  - ./data:/app/data                            # indeks Chroma — do zapisu
```

- **`:ro`** (read-only) dla ADC — kontener ma się uwierzytelnić, nie modyfikować
  Twoich poświadczeń. Zasada najmniejszych uprawnień.
- **Bez `:ro`** dla `./data` — i to nie przeoczenie: `chromadb.PersistentClient`
  otwiera swój magazyn SQLite w trybie zapisu **nawet przy samych odczytach**.
  Montaż read-only wywala start aplikacji.

Drugi punkt to typowa pułapka: „read-only jest bezpieczniejsze” bywa prawdą, ale
trzeba wiedzieć, czego biblioteka faktycznie potrzebuje. Komentarz w pliku
wyjaśnia to następnej osobie (albo Tobie za pół roku).

## `.dockerignore` — co NIE trafia do obrazu

Analogiczny do `.gitignore`, ale dotyczy *kontekstu builda*:

```
.venv/          # środowisko hosta, bezużyteczne i ciężkie
__pycache__/    # skompilowane .pyc z innej wersji Pythona
data/           # montowane w runtime, nie zapiekamy
.env            # sekrety nigdy nie wchodzą do obrazu
```

Sekrety w obrazie to problem trwały: obraz można wypchnąć do rejestru, a warstwy
zostają. Dlatego `.env` wstrzykujemy dopiero przy uruchomieniu (`env_file`),
a nie kopiujemy przy budowaniu.

## Test regresji — dlaczego był kluczowy

Scalenie plików compose mogło zepsuć DAG z Fazy 6. Sam fakt, że plik się parsuje
(`docker compose config`), niczego nie dowodzi. Dlatego uruchomiliśmy DAG
`dbt_transform` na nowej konfiguracji, przeciwko prawdziwemu BigQuery —
`dbt_run` i `dbt_test` zielone.

Przy okazji pułapka Airflow: **nowe DAG-i są domyślnie spauzowane**. Pierwsze
wyzwolenie utknęło w stanie `queued` i nic się nie działo. Potrzebne było
`airflow dags unpause dbt_transform`. Warto o tym pamiętać, zanim zacznie się
szukać błędu tam, gdzie go nie ma.

## Pojęcia do zapamiętania

- **Profil compose** — etykieta decydująca, które usługi startują.
- **`host.docker.internal`** — adres hosta widziany z wnętrza kontenera.
- **Martwa konfiguracja** — ustawienie, którego nikt nie odczytuje; wygląda
  poprawnie, nie działa. Weryfikuj przez uruchomienie, nie przez lekturę.
- **Kontekst builda** — pliki wysyłane do demona Dockera; ogranicza go `.dockerignore`.
- **Bind mount** — podpięcie katalogu hosta do kontenera (`:ro` = tylko odczyt).
