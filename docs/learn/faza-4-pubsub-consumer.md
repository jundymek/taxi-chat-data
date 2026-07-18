# Faza 4 — Pub/Sub consumer: batched streaming inserts do BigQuery

Notatka do nauki (PL). Kod, komentarze i docsy w repo są po angielsku — tutaj
tłumaczę *dlaczego* konsument (`ingestion/stream_consumer.py`) działa tak, a nie
inaczej.

## 1. Pull vs push — dlaczego pull

Pub/Sub oferuje dwa modele dostarczania:

- **push** — Pub/Sub sam robi HTTP POST na Twój endpoint, gdy pojawi się
  wiadomość. Potrzebujesz publicznego URL-a i serwera WWW.
- **pull** — Twój proces *sam* pyta o wiadomości (a właściwie: biblioteka
  kliencka utrzymuje streaming pull i woła Twój `callback`). Nie potrzeba
  publicznego endpointu — idealne do skryptu/joba, który sam się uruchamia.

Wybieramy **pull** (`subscriber.subscribe(sub_path, callback=...)`). To jest
tzw. *asynchronous pull*: biblioteka trzyma otwarty strumień gRPC, a każdą
przychodzącą wiadomość podaje do naszego `callback` **na wątku z puli** (stąd
`threading.Lock` — patrz niżej).

## 2. Flow control — po co limitować wiadomości „w locie"

```python
flow = pubsub_v1.types.FlowControl(max_messages=1000)
```

Bez limitu klient mógłby ściągnąć do pamięci dziesiątki tysięcy wiadomości
naraz, zanim zdążymy je zapisać — ryzyko OOM i tego, że *ack deadline* (u nas
30 s, ustawiony w Task 0 na subskrypcji) wygaśnie zanim dojdziemy do wiadomości.
Wygaśnięcie deadline = Pub/Sub uzna, że nie daliśmy rady, i **dostarczy
ponownie**. `FlowControl(max_messages=1000)` mówi: „trzymaj maksymalnie 1000
niezakończonych (unacked) wiadomości naraz". To zawór bezpieczeństwa — backpressure.

## 3. Semantyka ack/nack i *dlaczego ack DOPIERO po zapisie*

Kluczowa zasada at-least-once: **potwierdzasz odbiór (`ack`) dopiero wtedy, gdy
dane bezpiecznie wylądowały w BigQuery.**

- `ack()` = „mam to, nie wysyłaj ponownie" → Pub/Sub kasuje wiadomość.
- `nack()` = „nie dałem rady, wyślij ponownie" → Pub/Sub redostarcza.

Gdybyśmy potwierdzali *przed* zapisem (albo od razu w callbacku), to każdy błąd
BigQuery = **bezpowrotnie utracone dane**. Dlatego buforujemy wiersze i
`message` obok siebie, a `ack`/`nack` wykonujemy dopiero w `_flush_locked` po
odpowiedzi z `insert_rows_json`:

- insert bez błędów → `ack()` na **każdej** wiadomości z partii, licznik
  `inserted += len(rows)`.
- insert z błędami → `nack()` na **całej** partii (patrz punkt 5), nic nie
  potwierdzamy.

To jest świadomy wybór *at-least-once* (co najmniej raz), nie *exactly-once*.
W zamian za prostotę godzimy się na możliwe duplikaty — i rozwiązujemy je
osobnym mechanizmem (insertId, punkt 4).

## 4. `insertId` (= `trip_key`) jako best-effort dedup po stronie BQ

`insert_rows_json(table, rows, row_ids=[trip_key, ...])` — `row_ids` to
BigQuery **insertId**. Jeśli w krótkim oknie (BigQuery deduplikuje „best effort"
zwykle przez ok. 1 minutę) przyjdą dwa wiersze z tym samym `insertId`, BQ
zapisze tylko jeden.

Używamy `trip_key` (deterministyczny MD5 z kolumn klucza, liczony w
`stream_common`) jako insertId. Producent (alice) *celowo* wstrzykuje duplikaty
— publikuje **te same bajty** (ten sam `trip_key`) dwa razy, żeby zademonstrować
at-least-once. Dzięki insertId te duplikaty znikają po stronie BQ, mimo że
Pub/Sub dostarczył je dwukrotnie.

Ważne ograniczenia, o których trzeba wiedzieć:
- dedup insertId to **best-effort** i ma **okno czasowe** (~1 min). Duplikat,
  który przyjdzie dużo później (np. po długim nacku i redelivery), może się
  prześlizgnąć. To nie jest twarda gwarancja unikalności — twardą unikalność
  robi się dopiero downstream (np. `QUALIFY ROW_NUMBER()` / MERGE w hurtowni).
- dlatego mówimy „best-effort dedup", a nie „exactly-once".

## 5. Dlaczego nack **całej** partii przy błędzie insertu

`insert_rows_json` zwraca listę błędów per-wiersz. Moglibyśmy próbować nackować
tylko wiersze, które zawiodły — ale mapowanie „błąd → konkretna wiadomość" jest
kruche, a częściowe acki komplikują logikę. Wybieramy prostotę: **jeden błąd →
nack całej partii**. Pub/Sub redostarczy wszystkie, a te wiersze, które
*jednak* się zapisały, zostaną zdeduplikowane po insertId. To bezpieczne
właśnie dzięki punktowi 4 — redelivery bez dedupu robiłoby duplikaty.

## 6. Świadoma rezygnacja z dead-letter topic (malformed → log + ack + licznik)

Wiadomość, której nie da się zdekodować (`message_to_bq_row` rzuca
`ValueError` — nie-JSON albo brakuje pól), traktujemy tak:

```python
print(f"[consumer] rejected malformed message: {exc}")
self.rejected += 1
message.ack()
```

Czyli: logujemy, **potwierdzamy** (ack!) i zwiększamy licznik `rejected`.

Dlaczego ack, a nie nack? Bo malformed wiadomość jest „trująca" (*poison
message*) — nack tylko zapętliłby jej nieskończone redostarczanie, blokując
kolejkę. Ack ją usuwa.

Dlaczego nie dead-letter topic (DLT)? W produkcji *właśnie* skonfigurowałbyś
DLT: subskrypcja po N nieudanych próbach przerzuca wiadomość na osobny topic do
analizy, zamiast ją po cichu tracić. U nas (faza studyjna) świadomie
upraszczamy do „log + licznik" — widać ile odrzucono w końcowym podsumowaniu
(`seen/inserted/rejected`). W realu ciche gubienie danych bez DLT byłoby złe:
tracisz dowody, dlaczego coś nie weszło, i nie masz jak tego odtworzyć.

## 7. Zamykanie: flush częściowego bufora i timeout bezczynności

CLI ma dwa parametry sterujące życiem procesu:

- `--max-seconds` — co tyle sekund pętla główna woła `writer.flush()`, żeby
  **domknąć częściowy bufor** (gdy ruch jest mały i nie zbierze się pełna
  partia, wiersze i tak trafią do BQ, a nie utkną w pamięci).
- `--idle-timeout` — jeśli przez tyle sekund nie przyszła **żadna** wiadomość
  (`monotonic() - last_seen > idle_timeout`), proces się wyłącza. Dzięki temu
  demo/replay kończy się samo, bez wiszenia w nieskończoność.

Ważny szczegół: **nack też liczy się jako „aktywność"**. Gdy partię
zanackowaliśmy (np. po błędzie insertu), redelivery *dopiero nadejdzie* — więc
`BatchWriter` woła wtedy hook `on_retry`, który resetuje `last_seen`. Bez tego
timeout bezczynności mógłby wystrzelić między nackiem a redelivery i zamknąć
konsumenta, zanim dostałby z powrotem swoje własne wiadomości (utrata danych).
Kompromis: przy *trwałej* awarii BigQuery konsument zapętla się
(nack→redelivery→nack) zamiast wyjść — to widać w logach i jest lepsze niż ciche
wyjście z niedostarczonymi danymi; Ctrl-C zawsze go zatrzyma.

W `finally` zawsze robimy `future.cancel()` + `future.result()` (zatrzymanie
streaming pull) i **ostatni** `flush()`, żeby nie zgubić resztek z bufora, a na
końcu drukujemy `seen/inserted/rejected` — te liczniki czyta runbook w Task 3.
