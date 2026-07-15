# Faza 2: Pomiar optymalizacji (partycjonowanie + klasteryzacja)

## Partitioning + clustering scan measurement

- Unpartitioned scan (before): 71,969,952 bytes
- Partitioned + clustered scan (after): 2,271,816 bytes
- Reduction: 96.8%

> Zapytanie testowe: przejazdy z jednej strefy w jednym dniu.
> Pomiar przez BigQuery dry-run (bez wykonania, bez kosztu skanu).

## Jak zmierzono i dlaczego przez dry-run

Zamiast zgadywać, ile partycjonowanie + klastrowanie faktycznie daje,
zbudowano kontrolowany eksperyment: `marts.fct_trips_unpartitioned` to
dokładnie te same 2 998 748 wierszy co `fct_trips` (`CREATE TABLE ... AS
SELECT *`), ale bez `PARTITION BY` / `CLUSTER BY`. To samo zapytanie
analityczne (jeden dzień, jedna strefa odbioru) puszczono na obu tabelach z
`dry_run=True` — BigQuery wtedy **planuje** zapytanie i zwraca
`total_bytes_processed`, ale nic nie skanuje ani nie wykonuje (koszt = 0).
Dzięki temu porównanie "przed/po" jest metodologicznie czyste: jedyna różnica
między tabelami to fizyczny layout, więc cała różnica w bajtach jest
przypisywalna partycjonowaniu i klastrowaniu, a nie np. innym danym czy
cache'owi wyników (`use_query_cache=False`).

## Dlaczego wynik to redukcja o 96,8%

- **Partition pruning po `pickup_date`**: filtr `WHERE pickup_date =
  '2023-01-15'` na tabeli partycjonowanej sprawia, że silnik zapytań w ogóle
  nie dotyka pozostałych ~24 miesięcy danych — czyta tylko partycję
  odpowiadającą jednemu dniu. Na tabeli bez partycji ten sam filtr to zwykła
  kolumna, więc BigQuery musi przeskanować (prawie) całą tabelę, żeby
  odfiltrować wiersze.
- **Clustering po `pickup_location_id`**: w obrębie już wyciętej partycji
  dnia dodatkowy filtr `pickup_location_id = 161` korzysta z tego, że wiersze
  tej samej strefy leżą blisko siebie fizycznie (posortowane bloki) — silnik
  pomija bloki, w których na pewno nie ma pasującej strefy, zamiast czytać
  całą partycję dnia.
- Efekt łączny: z 71 969 952 bajtów (skan całej tabeli minus to, co i tak
  odsiewa metadana kolumnowa) do 2 271 816 bajtów (jedna partycja, przefiltrowana
  klastrowaniem) — ok. 32x mniej danych do przeczytania dla tego samego
  wyniku zapytania.

## Dlaczego to ważne (koszt = f(bajty))

BigQuery rozlicza zapytania **od ilości przeskanowanych bajtów**, nie od
czasu wykonania ani liczby zwróconych wierszy. To znaczy, że fizyczny układ
danych na dysku (partycje + klastry) jest bezpośrednią dźwignią kosztu i
wydajności — ta sama logika SQL, uruchomiona na tej samej ilości danych,
może kosztować 30x więcej lub mniej w zależności wyłącznie od tego, jak
tabela jest zorganizowana fizycznie. Dla typowych zapytań analitycznych w
tym projekcie (filtr po dacie i/lub strefie) to właśnie ten wybór — a nie np.
przepisywanie SQL-a — daje największą, zmierzoną (nie szacowaną) redukcję
kosztu.
