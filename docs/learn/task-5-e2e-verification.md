# Task 5: Weryfikacja end-to-end Fazy 1 — notatka do nauki

## Co zrobiliśmy

W tym zadaniu nie pisaliśmy nowego kodu — spięliśmy wszystko z Fazy 1 w jeden
przebieg i sprawdziliśmy, że cała droga danych działa od początku do końca.
Uruchomiliśmy `python -m ingestion.batch_load`, co po kolei: pominęło pobieranie
(plik już był na dysku — idempotencja z Taska 3), potwierdziło istnienie bucketu
GCS (idempotencja z Taska 4), wgrało plik Parquet do warstwy `raw/` w Data Lake,
utworzyło/potwierdziło dataset `raw` w BigQuery i załadowało dane do tabeli
`raw.trips`. Wynik: **3 066 766 wierszy**. Następnie niezależnie, poleceniem `bq
query`, wykonaliśmy zapytanie sanity — zakres dat odbioru pasażera oraz liczbę
wierszy — i na koniec zaktualizowaliśmy status Fazy 1 w `README.md`.

## Dlaczego takie decyzje

**Osobny krok "weryfikacja end-to-end".** Poszczególne moduły (`config`,
`download`, `batch_load`) mają własne testy, ale test jednostkowy sprawdza kawałek
w izolacji. Dopiero pełny przebieg całego pipeline'u na realnej infrastrukturze
GCP udowadnia, że moduły *składają się* w działającą całość: że config poprawnie
zasila download, download dostarcza plik, a batch_load wgrywa go i ładuje do
hurtowni. To jest różnica między "każdy klocek działa osobno" a "cała maszyna
działa" — w inżynierii danych ta druga gwarancja jest tą, na której naprawdę
zależy.

**Zapytanie sanity zamiast "ślepej wiary" w liczbę wierszy.** Sam fakt, że load
job zwrócił >0 wierszy, nie mówi, czy załadowały się *właściwe* dane. Zapytanie o
`MIN`/`MAX(tpep_pickup_datetime)` daje szybki, tani (skan jednej kolumny) obraz:
czy zakres dat mniej więcej pokrywa wybrany miesiąc (2023-01). To praktyka
"data sanity check" — minimalna walidacja poprawności danych po załadowaniu.

**Kluczowa obserwacja: surowe dane mają "brudne" wartości — i tak ma być.**
Zapytanie pokazało, że oprócz stycznia 2023 w danych są pojedyncze wartości
odstające — timestampy z 2008 roku czy z 1 lutego 2023. To nie jest błąd naszego
pipeline'u — to znana cecha surowych danych NYC TLC (źródło zawiera nieliczne
błędne rekordy). Ponieważ Faza 1 świadomie ładuje dane **surowe** (`raw`), bez
transformacji, te wartości odstające *powinny* tu przetrwać. Ich czyszczenie
(odrzucenie błędnych dat, ujemnych kwot, zerowego dystansu) to zadanie warstwy
staging w dbt w Fazie 2. Ta obserwacja jest wręcz dowodem, że decyzja
architektoniczna "ładuj surowo, transformuj później" działa zgodnie z zamysłem.

## Jakiej koncepcji to uczy

To jest **weryfikacja integracyjna pipeline'u danych** oraz wprowadzenie do
**walidacji jakości danych (data quality)**. W architekturze medallion warstwa
`raw` (brązowa) ma być wierną, nienaruszoną kopią źródła — łącznie z jego
niedoskonałościami — bo daje to możliwość powtórzenia (reprocessing) i audytu:
zawsze możemy wrócić do oryginału i przetransformować go inaczej. Dopiero warstwy
`staging` (srebrna) i `marts` (złota) nakładają czystość, typy i model
biznesowy. Rozdzielenie "wiernego załadowania" od "czyszczenia" to fundament
podejścia ELT (Extract-Load-Transform), na którym opierają się BigQuery + dbt,
Snowflake czy Databricks. Nauczyliśmy się też, że każdy załadowany zbiór danych
zasługuje na choćby minimalne zapytanie kontrolne — zaufanie do danych buduje się
przez weryfikację, nie przez założenie.
