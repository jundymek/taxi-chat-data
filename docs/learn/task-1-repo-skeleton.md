# Task 1: Szkielet repo — notatka do nauki

## Co zrobiliśmy

W tym zadaniu nie napisaliśmy jeszcze żadnej logiki biznesowej — celowo. Zbudowaliśmy
"szkielet" (scaffolding) repozytorium: `.gitignore`, `.env.example`, `requirements.txt`,
`README.md`, puste pakiety `ingestion/` i `tests/` oraz środowisko wirtualne `.venv`
z zainstalowanymi zależnościami. To fundament, na którym w kolejnych taskach (Faza 1)
staną moduły `ingestion/config.py`, `ingestion/download.py` i `ingestion/batch_load.py`,
odpowiedzialne za ściągnięcie danych NYC Taxi w formacie Parquet i załadowanie ich do
GCS oraz BigQuery.

## Dlaczego takie decyzje

**`.gitignore` i sekrety poza repo.** GCP wymaga plików z kluczami serwisowymi
(`credentials.json`, `*-key.json`) oraz zmiennych środowiskowych typu `GCP_PROJECT_ID`
czy `GCS_BUCKET`. Jeśli taki plik trafi do historii Gita — nawet po jego późniejszym
usunięciu — sekret pozostaje odzyskiwalny z historii commitów. Dlatego `.gitignore`
wyklucza `.env`, wszystkie warianty plików z kluczami oraz katalog `data/` i pliki
`*.parquet` (dane wejściowe potrafią ważyć setki MB — nie chcemy pompować tym repo
Gita, ani przypadkiem publikować cudzych danych).

**Wzorzec `.env.example`.** Zamiast trzymać rzeczywisty `.env` w repo (co byłoby
wyciekiem sekretów), commitujemy tylko `.env.example` — plik-szablon z nazwami
zmiennych i przykładowymi (nieprawdziwymi) wartościami. Każdy deweloper robi
`cp .env.example .env` i uzupełnia własne, prywatne wartości lokalnie. To standardowy
wzorzec w projektach 12-factor app: konfiguracja żyje w środowisku, nie w kodzie.

**Przypięte wersje w `requirements.txt`.** Używamy operatorów `>=` z konkretnym
minimalnym numerem wersji (np. `pandas>=2.2`) zamiast zostawiać wersje całkiem
otwarte. To kompromis między pełną reprodukowalnością (dokładne przypięcie `==`,
najlepiej przez `pip freeze` albo lockfile jak `poetry.lock`/`uv.lock`) a wygodą przy
szybko rozwijającym się projekcie nauki. W środowisku produkcyjnym dążyłoby się do
pełnego zamrożenia wersji, żeby build był deterministyczny i nie "psuł się" przy
nieoczekiwanym upgradzie zależności.

**Izolacja przez `.venv`.** Wirtualne środowisko Pythona odizolowuje zależności
projektu od systemowego Pythona i od innych projektów na tej samej maszynie. Dzięki
temu instalacja `google-cloud-storage`, `pyarrow` czy `pytest` w wersjach wymaganych
tutaj nie koliduje z inną wersją tych samych bibliotek gdzie indziej. `.venv/` jest
w `.gitignore` — środowisko jest efemeryczne i odtwarzalne jedną komendą
(`python3 -m venv .venv && pip install -r requirements.txt`), więc nie ma sensu go
wersjonować.

## Jakiej koncepcji to uczy

To jest w gruncie rzeczy praktyka **higieny DevSecOps** stosowana już na etapie
scaffoldingu projektu: sekrety nigdy nie trafiają do systemu kontroli wersji,
konfiguracja jest oddzielona od kodu, a środowisko uruchomieniowe jest reprodukowalne
i deklaratywne (widać dokładnie, jakich bibliotek i w jakich wersjach projekt wymaga).
W kontekście data engineeringu i pracy z pipeline'ami ingestii danych do chmury (GCS,
BigQuery) to szczególnie istotne — takie pipeline'y operują na poświadczeniach
z realnymi uprawnieniami do zasobów w chmurze, więc przypadkowy wyciek klucza
serwisowego ma realne konsekwencje bezpieczeństwa i kosztowe. Ta sama zasada
("sekrety i dane out-of-repo, zależności przypięte i izolowane") przenosi się wprost
na projekty GenAI, gdzie zamiast kluczy GCP chronimy klucze API do modeli LLM.
