# Faza 2 / Task 1: Szkielet projektu dbt w Dockerze — notatka do nauki

## Co zrobiliśmy

Zbudowaliśmy szkielet projektu dbt (`dbt/`) uruchamianego wyłącznie przez Dockera
(`docker-compose.yml`), łączącego się z BigQuery przez Application Default
Credentials (ADC) zamontowane z hosta jako wolumen tylko do odczytu. Nie ma tu
jeszcze żadnych modeli SQL — to warstwa konfiguracyjna: `dbt_project.yml` (nazwa
projektu, profil, ścieżki do modeli/seedów/makr, domyślne materializacje),
`profiles.yml` (połączenie do BigQuery: projekt `taxi-chat-data`, lokalizacja
`US`, metoda auth `oauth`), `packages.yml` (zależność `dbt_utils`) oraz
makro `generate_schema_name.sql`. Zweryfikowaliśmy działanie realnym
`docker compose run --rm dbt debug` (zakończone `All checks passed!` z żywym
połączeniem do BigQuery) oraz `dbt parse`.

## Czym jest dbt i warstwowanie "medallion"

dbt (data build tool) to narzędzie do warstwy **T** w ELT (Extract-Load-
Transform) — w odróżnieniu od klasycznego ETL, najpierw ładujemy surowe dane
do hurtowni (Faza 1: `raw.trips` w BigQuery), a dopiero potem transformujemy je
SQL-em *wewnątrz* silnika bazy danych. dbt nie przenosi danych — generuje i
uruchamia zapytania `CREATE VIEW`/`CREATE TABLE AS SELECT` na podstawie
modeli `.sql`, zarządza zależnościami między nimi (DAG) i pilnuje testów oraz
dokumentacji jako część kodu.

Architektura "medallion" (znana z Databricks, ale stosowana też z BigQuery)
dzieli transformacje na warstwy o rosnącej jakości i użyteczności biznesowej:

- **raw / bronze** — surowe dane 1:1 ze źródła (u nas: `raw.trips` z Fazy 1,
  bez zmian, z ewentualnymi błędami i duplikatami).
- **staging / silver** — czyszczenie: rzutowanie typów, ujednolicenie nazw
  kolumn, odrzucenie oczywistych śmieci, ale wciąż na poziomie granularności
  źródła (u nas: dataset `staging`, materializacja `view` — tanio, bo widok
  nie kopiuje danych, tylko przelicza zapytanie na żądanie).
- **marts / gold** — modele biznesowe: wymiary i tabela faktów w schemacie
  gwiazdy, zoptymalizowane pod konkretne pytania analityczne (u nas: dataset
  `marts`, materializacja `table` — kosztowniej przy budowie, ale szybko przy
  odpytywaniu, co ma sens dla warstwy konsumowanej przez BI/czat).

To zadanie ustawia tylko szkielet (`+schema: staging` / `+schema: marts` w
`dbt_project.yml`) — same modele stagingowe i marty przyjdą w kolejnych
taskach.

## Dlaczego dbt uruchamiamy w Dockerze

Alternatywą byłoby zainstalowanie `dbt-bigquery` lokalnie przez pip/venv, tak
jak zrobiliśmy to dla `ingestion/` w Fazie 1. Wybraliśmy jednak kontener,
bo:

1. **Reprodukowalność środowiska uruchomieniowego.** `dbt-core` i adaptery
   (`dbt-bigquery`) są wrażliwe na wersje Pythona i zależności — obraz Docker
   z przypiętą wersją bazową (`python:3.12-slim`) gwarantuje, że
   `docker compose run --rm dbt <cmd>` daje identyczny wynik na moim laptopie,
   na innym laptopie i (docelowo) w CI, niezależnie od tego, co jest
   zainstalowane lokalnie.
2. **Ścieżka do Fazy 6 (orkiestracja).** W Fazie 6 dbt ma być uruchamiany
   przez Airflow. Airflow też będzie żył w Dockerze (docker-compose ze
   scheduler/webserver/worker), więc już teraz przygotowujemy dbt jako
   niezależny, kontenerowy "krok pipeline'u" — Airflow (`DockerOperator` albo
   `BashOperator` wołający `docker compose run`) będzie mógł go uruchomić
   dokładnie tak samo, jak my robimy to ręcznie teraz.
3. **Izolacja od hosta.** Kontener nie zależy od tego, czy na hoście jest
   zainstalowany Python 3.12, konkretna wersja `dbt-bigquery` czy `git` w
   odpowiedniej wersji — wszystko to definiuje `dbt/Dockerfile`.

## Dlaczego ADC przez mount, a nie plik z kluczem service account

Tak jak w Fazie 1 (batch ingestion), **nie** trzymamy nigdzie w repo pliku
`credentials.json`/`*-key.json` z kluczem service accounta. Zamiast tego
`docker-compose.yml` montuje katalog `~/.config/gcloud` z hosta do kontenera
w trybie tylko do odczytu (`:ro`):

```yaml
volumes:
  - ~/.config/gcloud:/root/.config/gcloud:ro
```

Kontener "pożycza" tożsamość zalogowanego na hoście `gcloud auth
application-default login` — dbt łączy się z BigQuery jako ja (moje konto
Google), z moimi uprawnieniami IAM, bez żadnego dodatkowego sekretu w
systemie plików repo. Zalety tego podejścia:

- **Zero sekretów w repo i w obrazie Dockera.** Nawet gdyby ktoś dostał się
  do kodu źródłowego albo do zbudowanego obrazu, nie znajdzie tam nic do
  wykradzenia — poświadczenia istnieją tylko na hoście i są montowane w
  runtime.
- **Odwoływalność.** Jeśli trzeba cofnąć dostęp, wystarczy `gcloud auth
  revoke` na hoście — nie trzeba rotować kluczy w N różnych miejscach.
- **Ten sam model bezpieczeństwa co w Fazie 1**, więc konsekwentna postawa
  bezpieczeństwa w całym projekcie: ADC zamiast kluczy service account
  wszędzie, gdzie to możliwe.

Tryb `:ro` (read-only) dodatkowo gwarantuje, że proces w kontenerze nie może
nadpisać czy skasować poświadczeń na hoście, nawet gdyby chciał (np. przez
błąd w jakimś skrypcie).

## Detal: `generate_schema_name` i dokładne nazwy datasetów

dbt-bigquery domyślnie **skleja** schemat docelowy z `target.schema` profilu
i wartością `+schema` z configu modelu (np. `staging_marts`), żeby uniknąć
przypadkowych kolizji między różnymi zespołami/środowiskami współdzielącymi
jeden profil. My chcemy jednak dokładnie `staging` i `marts` — bez
sklejania — bo to jednoosobowy projekt nauki z jasno rozdzielonymi
datasetami. Dlatego nadpisujemy domyślne makro `generate_schema_name` tak, by
używało `custom_schema_name` **dosłownie**, gdy jest podane, a `target.schema`
tylko gdy modele go nie definiują. To dobry przykład tego, jak dbt pozwala
nadpisywać wbudowane zachowania przez zwykłe makra Jinja we własnym projekcie
— nie trzeba grzebać w kodzie adaptera.

## Czego uczy ten koncept

- **Warstwa transformacji w ELT** — SQL jako język transformacji "w miejscu",
  bez przenoszenia danych poza silnik bazy.
- **Izolacja środowiska uruchomieniowego** przez konteneryzację — ten sam
  obraz działa identycznie wszędzie, co jest fundamentem pod przyszłą
  orkiestrację (Airflow, Faza 6).
- **Konfiguracja jako kod (IaC-style)** — cały projekt dbt (profil,
  materializacje, schematy, zależności pakietów) jest zdefiniowany
  deklaratywnie w plikach YAML wersjonowanych w Gicie, a nie ustawiany
  ręcznie przez UI czy komendy jednorazowe.
- **Bezpieczeństwo przez pożyczoną tożsamość (ADC)** zamiast dystrybuowanych
  sekretów — wzorzec, który skaluje się też na CI/CD (np. Workload Identity
  Federation zamiast kluczy JSON).
