# Task 2: Config z env — notatka do nauki

## Co zrobiliśmy

Zbudowaliśmy moduł `ingestion/config.py`, który jest jedynym miejscem w kodzie
odpowiedzialnym za odczyt konfiguracji ze zmiennych środowiskowych. Sercem modułu jest
dataclass `Config` z sześcioma polami (`project_id`, `bucket`, `dataset_raw`,
`location`, `data_dir`, `taxi_month`) oraz funkcja `load_config() -> Config`, która
czyta odpowiednie zmienne env (`GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET_RAW`,
`BQ_LOCATION`, `TAXI_DATA_DIR`, `TAXI_MONTH`), waliduje je i zwraca gotowy obiekt.
Na starcie modułu wywołujemy `load_dotenv()` z biblioteki `python-dotenv`, co
automatycznie wczyta plik `.env` (stworzony na bazie `.env.example` z Taska 1) do
środowiska procesu — ale tylko dla zmiennych, które nie są już ustawione systemowo,
bo `python-dotenv` domyślnie nie nadpisuje istniejących zmiennych env. Pisaliśmy to
metodą TDD: najpierw `tests/test_config.py` (czerwony test — `ModuleNotFoundError`,
bo `ingestion/config.py` jeszcze nie istniał), potem minimalna implementacja, która
sprawia, że oba testy przechodzą.

## Dlaczego takie decyzje

**Jedno źródło prawdy (single source of truth) dla konfiguracji.** Zamiast rozrzucać
`os.getenv(...)` po całym kodzie ingestii (`download.py`, `batch_load.py` w kolejnych
taskach), cała wiedza o tym, jakie zmienne env istnieją, jak się nazywają i jakie mają
wartości domyślne, żyje w jednym module. Gdy w przyszłości dojdzie nowa zmienna
konfiguracyjna, zmienia się tylko `config.py` — reszta kodu korzysta z gotowego,
typowanego obiektu `Config`, a nie z surowych stringów ze środowiska.

**Fail-fast zamiast cichego psucia się później.** Pola `project_id` i `bucket` są
wymagane — bez nich pipeline nie ma jak zapisać danych do GCS ani odwołać się do
właściwego projektu GCP. `load_config()` rzuca `ValueError` z czytelnym komunikatem
natychmiast, na starcie programu, zamiast pozwolić, by brak konfiguracji ujawnił się
dopiero głęboko w trakcie wykonania (np. jako tajemniczy błąd autoryzacji API Google
Cloud po dziesięciu minutach przetwarzania). To klasyczna zasada "fail fast, fail
loud" — im wcześniej wykryjemy błąd konfiguracji, tym taniej go naprawić.

**Wymagane pola vs. wartości domyślne.** Pozostałe cztery pola (`dataset_raw`,
`location`, `data_dir`, `taxi_month`) mają sensowne wartości domyślne (`"raw"`,
`"US"`, `"./data"`, `"2023-01"`), bo to parametry, które w tym projekcie nauki rzadko
się zmieniają i mają rozsądny fallback. Rozróżnienie "to musi być jawnie podane" od
"to ma bezpieczną wartość domyślną" to świadoma decyzja projektowa — wymuszamy
jawność tam, gdzie błąd byłby kosztowny (zły projekt GCP, zły bucket), a ułatwiamy
życie tam, gdzie domyślna wartość jest wystarczająca.

**Precedencja: env systemowy > `.env`.** `load_dotenv()` nie nadpisuje zmiennych już
ustawionych w środowisku procesu. Dzięki temu w CI/CD albo w kontenerze produkcyjnym,
gdzie sekrety wstrzykuje się przez prawdziwe zmienne środowiskowe (np. GitHub Actions
secrets, Cloud Run env vars), plik `.env` — jeśli w ogóle istnieje — nie może
przypadkiem nadpisać bezpieczniejszej konfiguracji z platformy uruchomieniowej.

## Jakiej koncepcji to uczy

To bezpośrednia implementacja zasady **III. Config** z metodyki
[12-factor app](https://12factor.net/config): konfiguracja, która różni się między
środowiskami (dev/staging/prod), musi żyć w środowisku (zmiennych env), nie w kodzie
źródłowym ani w plikach konfiguracyjnych wersjonowanych razem z aplikacją. Wzorzec
"jeden dataclass + jedna funkcja ładująca + walidacja wymaganych pól" to też przykład
**configuration-as-code** połączonego z **fail-fast validation** — coś, co w większych
systemach danych realizują biblioteki jak Pydantic Settings albo Dynaconf, ale zasada
jest identyczna niezależnie od skali. W kontekście GenAI ten sam wzorzec chroni klucze
API do LLM-ów (np. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) — aplikacja, która rzuca
czytelny błąd przy starcie z powodu brakującego klucza API, jest dużo łatwiejsza
w debugowaniu niż taka, która zawiedzie dopiero przy pierwszym wywołaniu modelu.
