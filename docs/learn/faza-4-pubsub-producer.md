# Faza 4 — Producent Pub/Sub (notatka do nauki)

> Notatka po polsku (materiał do nauki). Kod, komentarze i commity są po
> angielsku — to jest warstwa infrastruktury.

## O co chodzi w tym tasku

Piszemy **producenta**: program, który czyta lokalny plik Parquet z przejazdami
taksówek i „udaje" żywy strumień danych, wypychając kolejne przejazdy do
**Google Cloud Pub/Sub**. To symulacja streamingu — nie mamy prawdziwego źródła
na żywo, więc odtwarzamy (ang. *replay*) dane historyczne z kontrolą tempa.

Cały sens Fazy 4 to pokazać **at-least-once delivery** i **deduplikację** na
żywo. Producent musi więc celowo generować duplikaty, żeby konsument (Task 2,
kolega bob) miał co deduplikować.

## Czym jest Pub/Sub (w skrócie)

Pub/Sub to broker wiadomości typu **publish/subscribe**:

- **Topic** (temat) — nazwana „skrzynka", do której *publikujemy* wiadomości.
- **Subscription** (subskrypcja) — z niej *konsument odbiera* wiadomości. Jeden
  topic może mieć wiele subskrypcji (każda dostaje własną kopię).
- **Message** — bajty (`data`) + opcjonalne **atrybuty** (`attributes`), czyli
  para klucz–wartość obok właściwej treści.

Kluczowa własność: Pub/Sub gwarantuje dostarczenie **co najmniej raz**
(*at-least-once*). Znaczy to, że ta sama wiadomość może dotrzeć **więcej niż
raz** (np. przy retry po braku ack). Dlatego konsument musi umieć rozpoznać
duplikat — u nas po kluczu `trip_key` (jako `insertId` w BigQuery).

## Payload vs atrybuty

W każdej wiadomości mamy dwa miejsca na dane:

- **Payload** (`data`, bajty) — właściwa treść przejazdu. U nas: JSON z 19
  kolumnami + `trip_key`, zbudowany przez `row_to_message` z modułu-kontraktu
  `stream_common` (Task 0). Producent **nie** serializuje ręcznie — używa
  jednej, wspólnej funkcji, żeby producent i konsument zgadzali się co do bajtów.
- **Atrybuty** — lekkie metadane, które można czytać **bez** dekodowania
  payloadu. Ustawiamy dwa: `trip_key` (do routingu/podglądu) oraz
  `source="replay"` (skąd pochodzi wiadomość). `source` żyje TYLKO w atrybutach,
  nie w payloadzie — konsument mapuje w payloadzie wyłącznie `MESSAGE_FIELDS` +
  `trip_key`, więc dorzucenie klucza do treści by go zaskoczyło.

## Dlaczego `publish()` zwraca *future* i po co zbieramy futures

`publisher.publish(...)` **nie** wysyła od razu i nie czeka na potwierdzenie —
zwraca **future** (obietnicę wyniku). Klient buforuje wiadomości i wysyła je
partiami w tle. To wydajne, ale ma pułapkę: jeśli nigdy nie sprawdzimy wyniku,
błąd publikacji przejdzie **niezauważony**.

Dlatego:

```python
futures.append(publisher.publish(topic_path, data, **attrs))
...
for future in futures:
    future.result(timeout=60)   # tu wychodzi ewentualny wyjątek
```

Zbieramy wszystkie futures i na końcu wołamy `.result()`. `result()` blokuje aż
do potwierdzenia (albo rzuca wyjątek). Dzięki temu funkcja `replay` kończy się
dopiero, gdy **wszystko** faktycznie trafiło do Pub/Sub — a nie tylko wpadło do
lokalnego bufora.

## Throttling — po co spowalniać

Gdybyśmy wypchnęli 100 tys. wierszy najszybciej jak się da, nie wyglądałoby to
jak żywy feed (i obciążyłoby wszystko naraz). `--rate` (msg/s) wymusza **średnie**
tempo:

```python
expected_elapsed = published / rate          # ile czasu POWINNO minąć
sleep_for = expected_elapsed - faktyczny_czas
if sleep_for > 0:
    time.sleep(sleep_for)
```

Liczymy, ile czasu *powinno* zająć wysłanie `published` wiadomości przy zadanym
tempie, i dosypiamy sen do tej wartości. To sterowanie **do średniej** — samo się
koryguje, gdy publikacja chwilowo zwolni (inaczej niż sztywny `sleep(1/rate)` po
każdej wiadomości). `--rate 0` = bez throttlingu (przydatne w testach).

## Dlaczego duplikaty wstrzykujemy CELOWO

To najważniejsza decyzja projektowa. Bez sztucznych duplikatów „nauka
deduplikacji" byłaby czysto teoretyczna — konsument nigdy nie zobaczyłby
powtórki. Dlatego z prawdopodobieństwem `--dup-rate` publikujemy tę samą
wiadomość **drugi raz**:

```python
if rng.random() < dup_rate:
    futures.append(publisher.publish(topic_path, data, **attrs))  # TE SAME bajty
    duplicates += 1
```

**Duplikat = te same bajty, ten sam `trip_key`, opublikowane dwa razy.** To nie
jest inny wiersz ani przeliczony na nowo klucz — to dokładnie ta sama wiadomość.
Dzięki temu konsument, deduplikując po `insertId = trip_key`, faktycznie ma co
scalić. `rng` (generator losowy) wstrzykujemy jako argument, żeby w testach
podstawić deterministyczny skrypt liczb i dokładnie kontrolować, który wiersz się
zduplikuje.

## Co zwraca `replay`

Słownik `{"published": int, "duplicates": int}`:

- `published` — liczba **unikalnych** przejazdów (bez duplikatów),
- `duplicates` — ile dodatkowych kopii wstrzyknęliśmy.

Łączna liczba wywołań `publish` = `published + duplicates`. Ten kontrakt (kształt
słownika) jest tym, na czym opierają się testy i runbook Task 3 — dlatego nie
zmieniamy go samowolnie.

## Testowanie bez GCP

Testy jednostkowe **nie** dotykają żywego Pub/Sub (kosztowne i wolne).
Podstawiamy `FakePublisher`, który zapisuje wywołania `publish` do listy, oraz
`FakeFuture`, którego `result()` zwraca stały string. Dzięki wstrzyknięciu
`publisher` i `rng` jako argumentów `replay`, całą logikę (limit, duplikaty,
atrybuty) sprawdzamy w pamięci, w milisekundach, offline.

## Najważniejsze do zapamiętania

1. Pub/Sub = at-least-once → duplikaty są **normalne**, konsument musi dedupować.
2. Bajty wiadomości pochodzą z **jednej wspólnej funkcji** (`row_to_message`) —
   producent i konsument nie zgadują formatu.
3. `publish()` jest asynchroniczny → zbieraj futures i wołaj `result()`.
4. Payload vs atrybuty — `source` jest w atrybutach, nie w treści.
5. Duplikaty wstrzykujemy celowo (te same bajty), inaczej nie ma czego uczyć.
