# B-API: Routing von KI-Modellen

Stand 2026-10-01 · alle Beispiele gegen Staging ausgeführt
(`https://b-api.staging.openeduhub.net`) · Messwerte und Belege im
[Testbericht vom selben Tag](audits/2026-10-01-bapi-router.md)

## Kurz gesagt

- Eine **Route** ist ein Name für eine Gruppe von KI-Modellen — auch über
  Provider hinweg, etwa OpenAI und AcademicCloud zusammen.
- Anwendungen schicken den Routennamen im Feld `model` an
  `/api/v1/llm/router/…`, genau so, wie sie sonst einen Modellnamen schicken.
- Die B-API wählt das Modell selbst: zuerst nach **Stufe** (Priorität), dann
  nach **Gewicht** — und weicht auf ein anderes aus, wenn eines nicht antwortet.
- Modelle lassen sich so zentral austauschen, ohne die Anwendungen anzufassen —
  solange das neue Modell dieselben Anfrage-Parameter versteht (siehe
  [Worauf man achten muss](#worauf-man-achten-muss)).
- Es geht auch ohne Route: `openai/gpt-5.6-luna` spricht ein Modell direkt über
  den Router an.

## Auf einen Blick: geprüft am 2026-10-01

Alles gegen Staging, mit eigenen Wegwerf-Routen, die danach wieder gelöscht
wurden; Modelle wurden nur mit `gpt-5.6-luna` aufgerufen. Messwerte und Belege
stehen im [Testbericht](audits/2026-10-01-bapi-router.md).

### Bestätigt

| Funktion | Ergebnis |
|---|---|
| Anfragen über eine Route (`chat/completions`, `responses`) | funktioniert; die Antwort hat das OpenAI-Format |
| Muster `provider/modell` ohne Route | funktioniert, etwa mit `openai/gpt-5.6-luna` |
| Eigene Routen anlegen, ändern und löschen über die API | funktioniert; jede Änderung wirkt sofort |
| Eigene Route vor globaler Route gleichen Namens | bestätigt: die eigene antwortet |
| Route mit Musternamen (`openai/…`) vor dem Muster | bestätigt |
| Unbekannter, deaktivierter oder gelöschter Name | sofort `400 No route configured` |
| Ausweichen auf die nächste Stufe | bestätigt, wenn ein Eintrag nicht nutzbar ist (hier: Modell ohne Preis) |
| Einträge abschalten | abgeschaltete werden übersprungen; sind alle aus, kommt 503 |
| Cache der Route und des Providers | wortgleiche Anfragen kommen in Millisekunden aus dem Cache; das Muster teilt den Cache des Providers |
| `ignore-caching`, `clear-cache` und `clearCache` | wirken wie beschrieben |
| Prüfung beim Anlegen | doppelte Kennungen, unbekannte Provider, Gewicht 0, `maxAttempts` außerhalb von 1–10, leere Namen und leere Listen: 400; doppelter Routenname: 409 |
| Was ein Konto sieht | `/routes` zeigt eigene und aktive globale Routen, `/models` nur aktive; das Muster steht in keiner Liste |
| Standardwerte | ohne Angabe: Stufe 0, Gewicht 1, aktiv |
| Anmeldung | `X-API-KEY` und `Authorization: Bearer`; ohne oder mit falschem Schlüssel: 401 |

### Nicht korrekt oder anders als beschrieben

| Befund | Was passiert | Vorschlag |
|---|---|---|
| Dauerhafte Fehler kommen als 503 | Modell ohne Preis (auch ein Tippfehler hinter `openai/…`), eine Route ohne aktiven Eintrag und ein Modell am falschen Endpunkt melden 503 — Clients mit Wiederholungslogik warten umsonst | 400 mit klarer Meldung; 503 nur für Vorübergehendes |
| Gecachte Antworten sind nicht erkennbar | dieselbe `id`, dieselbe Zeit, dieselbe Token-Zählung — keine Kennzeichnung | eine Kopfzeile, etwa `X-Cache: HIT` |
| Der antwortende Eintrag ist nicht erkennbar | nur das Feld `model` nennt das Modell — nicht den Provider, nicht die Kennung | Kopfzeilen wie `X-Route` und `X-Route-Deployment` |
| Eine Route ohne aktiven Eintrag wird gelistet | sie steht in `/models`, antwortet aber mit 503 | nicht listen |
| Das Modell wird beim Anlegen nicht geprüft | jeder Name wird angenommen, auch einer, den es nicht gibt | prüfen oder warnen |
| Gewichte | die erste Fassung sagte „0,5 = 50/50"; es sind ganze Zahlen ab 1. Die API-Beschreibung erlaubt 0, der Server nicht | Doku und API-Beschreibung angleichen |
| Max. Versuche | die erste Fassung sagte „Versuche je Modell", die API-Beschreibung „Aufrufe je Anfrage". Mit dem Wert 1 wurde trotzdem ausgewichen | Bedeutung festlegen und an beiden Stellen gleich beschreiben |
| Statuscodes | 404 (unbekannte `id`) und 409 (doppelter Name) fehlen in der API-Beschreibung; die 404 kommt ohne Meldung | ergänzen, Meldung mitschicken |
| Zwei Fehlerformen | `{"error": "…"}` und `{"<feld>": "…"}` | eine Form |
| Zeitstempel | UTC, aber ohne Zeitzonenangabe | mit `Z` ausgeben |
| `accountId` in der API-Beschreibung | „leer = globale Route" — am Konto-Endpunkt wird die Route aber dem eigenen Konto zugeordnet | Text anpassen |

### Nicht geprüft

Die gewichtete Verteilung und das Ausweichen nach einem echten Ausfall (beides
braucht unterscheidbare Modelle), das Merken nicht erreichbarer Modelle,
andere Endpunkte mit passenden Modellen, die Admin-Endpunkte, mehrere
B-API-Instanzen und das Abschalten des Musters. Fragen zu Rechten und Kosten
hat das B-API-Team gesondert bekommen.

## Begriffe

| Begriff | In der B-API-UI | Im JSON der API | Bedeutung |
|---|---|---|---|
| Route | Routenname (Modell) | `logicalModel` | der Name, den Anwendungen als `model` schicken |
| Beschreibung | Beschreibung | `description` | freier Text |
| Route aktiv | Route aktiv | `enabled` | aus: der Name ist unbekannt (400) |
| Max. Versuche | Max. Versuche | `maxAttempts` | 1–10; leer = Standard der B-API |
| Eintrag | eine Zeile unter „Deployments" | ein Element in `deployments` | ein Modell bei einem Provider |
| Provider | Provider | `providerId` | `openai` oder `academiccloud` |
| Modell | Modell beim Provider | `upstreamModel` | der Modellname beim Provider |
| Kennung | Kennung | `id` (im Eintrag) | frei wählbar, je Route eindeutig; erscheint in Logs und Fehlermeldungen |
| Stufe | Priorität | `priorityTier` | 0 kommt zuerst |
| Gewicht | Gewicht | `weight` | ganze Zahl ab 1; Anteil innerhalb einer Stufe |
| Eintrag aktiv | Aktiv | `enabled` (im Eintrag) | aus: der Eintrag wird übersprungen |
| Cache leeren | Cache dieser Route beim Speichern leeren | `clearCache` | nur beim Ändern einer Route |

## Globale Routen und Konto-Routen

Beide sind gleich aufgebaut. Sie unterscheiden sich darin, wem sie gehören und
für wen sie gelten.

- **Globale Routen** gehören keinem Konto und gelten für alle. Administratoren
  pflegen sie in der B-API-UI auf der Seite „LLM-Routing" (oder über die
  Admin-Endpunkte).
- **Konto-Routen** gehören einem Konto und gelten nur für dessen API-Schlüssel.
  Gepflegt werden sie in der UI am Konto im Tab „LLM-Routen" — oder vom Konto
  selbst über die API, wenn es das Recht `LLM_ROUTE_MANAGE` hat.
- **Gleicher Name:** Für ein Konto gilt seine eigene aktive Route, alle anderen
  Konten nutzen weiter die globale. Ist die eigene Route deaktiviert, greift für
  dieses Konto wieder die globale.
- **Was ein Konto sieht:** `GET /api/v1/llm/router/routes` liefert die eigenen
  Routen (auch deaktivierte) und die aktiven globalen — keine Routen anderer
  Konten. Globale Routen erkennt man an `"accountId": null`.

## Welcher Name wohin führt

Der Router prüft den Namen im Feld `model` in dieser Reihenfolge; die erste
passende Stufe gilt.

| Stufe | Wenn … | dann … |
|---|---|---|
| 1 | das Konto eine **aktive** Route dieses Namens hat | eines ihrer Modelle (Stufe, Gewicht, Ausweichen), Cache der Route |
| 2 | sonst eine **aktive globale** Route dieses Namens existiert | wie bei 1 |
| 3 | sonst der Name die Form `provider/modell` hat und der Provider bekannt ist | direkt an diesen Provider: ein Ziel, kein Ausweichen, Cache des Providers |
| – | nichts davon passt | `400 No route configured for model '…'` |

- Eine Route, die selbst wie ein Muster heißt (etwa `openai/spezial`), gewinnt
  vor dem Muster.
- Ein bloßer Modellname wie `gpt-5.6-luna` ist **kein** Muster. Ohne
  gleichnamige Route endet er mit 400 — wichtig bei der
  [Umstellung](#bestehende-anwendungen-umstellen).

## Ohne Route: das Muster `provider/modell`

- Provider, Schrägstrich, Modellname beim Provider: `openai/gpt-5.6-luna`,
  `academiccloud/gemma-4-31b-it`. Geteilt wird am ersten `/` —
  `academiccloud/meta-llama/Llama-3` meint das Modell `meta-llama/Llama-3`.
- Genau ein Ziel: keine Stufen, keine Gewichte, kein Ausweichen. Fehler des
  Providers kommen so zurück, wie er sie schickt.
- Derselbe Cache wie beim direkten Aufruf (`/api/v1/llm/openai/…`): Antworten
  werden geteilt.
- Rechte, Kontingente und Kosten gelten wie beim Provider; ein Konto erreicht
  nur Provider, für die es berechtigt ist.
- Das Modell braucht in der B-API einen Preis (Admin-Bereich „Model Pricing").
  Sonst endet der Aufruf mit `503 Model pricing unavailable`.
- Das Muster steht nicht in `GET …/router/models`. In den Nutzungsdaten
  erscheint der Aufruf ohne Route, mit der Kennung `provider-prefix`.
- Abschaltbar über `app.llm.routing.providerPrefixFallback=false` (Standard:
  an). Dann führen nur noch Routen ans Ziel.

## Wie eine Route ein Modell wählt

- **Stufe** (`priorityTier`): 0 kommt zuerst. Eine höhere Stufe kommt erst
  dran, wenn kein Eintrag der niedrigeren antwortet — etwa Stufe 0 für die
  Hauptmodelle, Stufe 1 als Reserve.
- **Gewicht** (`weight`): eine ganze Zahl ab 1, wirksam nur innerhalb einer
  Stufe und relativ zu den anderen. 1 und 1 heißt je etwa die Hälfte; 3, 1 und 1
  heißt etwa 60, 20 und 20 Prozent. 0 und Kommazahlen sind nicht erlaubt.
- **Eintrag abschalten** (`enabled: false`) nimmt ein Modell aus der Auswahl,
  ohne es zu löschen.
- **Max. Versuche** (`maxAttempts`, 1–10, leer = Standard der B-API): laut
  API-Beschreibung die Höchstzahl an Aufrufen bei Providern je Anfrage. Ob das
  insgesamt oder je Modell gemeint ist, ist noch zu klären. Wer Ausweichen will,
  setzt den Wert nicht auf 1.
- **Nicht erreichbare Modelle** merkt sich die B-API für eine Weile und
  überspringt sie.
- **Auslastung** der AcademicCloud-Modelle fließt nicht ein; verteilt wird nur
  nach Stufe und Gewicht.
- **Wer geantwortet hat**, steht im Feld `model` der Antwort (etwa
  `"gpt-5.6-luna"`) — ohne Provider und ohne Kennung. Eine Kopfzeile dafür gibt
  es nicht.

## Der Cache

- Die B-API merkt sich Antworten. Eine **wortgleiche** Anfrage bekommt die
  gespeicherte Antwort zurück — in Millisekunden, mit derselben `id`, ohne
  Kennzeichnung. Wer bewusst neue Antworten will, muss den Cache umgehen.
- Routen haben einen **eigenen** Cache, das Muster nutzt den des Providers. Nach
  dem Umstieg auf eine Route beginnt der Cache also leer.
- **Änderungen an einer Route leeren den Cache nicht.** Nach einem Modelltausch
  kommen sonst weiter Antworten des alten Modells. Darum beim Speichern „Cache
  dieser Route beim Speichern leeren" einschalten (API: `"clearCache": true`).
- Je Anfrage steuerbar über Parameter in der Adresse:
  - `?ignore-caching=true` — neue Antwort, die nicht gespeichert wird
  - `?clear-cache=true` — neue Antwort, die die gespeicherte ersetzt
- Wie lange Antworten gespeichert bleiben, ist von außen nicht zu sehen.

## Die Endpunkte

Anmeldung bei jedem Aufruf mit dem Header `X-API-KEY: <Schlüssel>`
(`Authorization: Bearer <Schlüssel>` geht auch). Ohne oder mit falschem
Schlüssel: 401. Die vollständige Beschreibung steht in der Swagger-UI der
B-API, Gruppe „API Router" (`/v3/api-docs/router`).

**Nutzen** — OpenAI-kompatibel, alle unter `/api/v1/llm/router/`:

| Endpunkt | Wofür |
|---|---|
| `GET models` | die Namen der nutzbaren Routen |
| `POST chat/completions` | Chat |
| `POST responses`, `POST responses/input_tokens` | Responses-API, Token zählen |
| `POST completions` | ältere Textvervollständigung |
| `POST embeddings` | Vektoren |
| `POST moderations` | Moderation |
| `POST images/generations`, `images/edits`, `images/variations` | Bilder |
| `POST audio/speech`, `audio/transcriptions`, `audio/translations` | Sprache |

Jeder Endpunkt funktioniert nur mit Modellen, die das jeweilige können — etwa
`embeddings` nur mit einem Embedding-Modell.

**Verwalten** — eigene Routen, mit dem Recht `LLM_ROUTE_MANAGE`:

| Endpunkt | Wofür |
|---|---|
| `GET /api/v1/llm/router/routes` | eigene und aktive globale Routen, mit allen Einträgen |
| `POST /api/v1/llm/router/routes` | eine Route anlegen |
| `PUT /api/v1/llm/router/routes/{id}` | eine Route ersetzen |
| `DELETE /api/v1/llm/router/routes/{id}` | eine Route löschen |

Globale Routen verwalten Administratoren unter `/administration/llm-routing/…`
— nicht Teil dieses Dokuments.

## Schritt für Schritt — mit Beispielen

Die Beispiele sind für die Kommandozeile (macOS, Linux oder Git Bash unter
Windows). Vorher einmal setzen:

```bash
export B=https://b-api.staging.openeduhub.net
export B_API_KEY=...   # eigener Schlüssel; nie in Dateien, Tickets oder Chats kopieren
```

### 1. Welche Routen kann ich nutzen?

```bash
curl -s "$B/api/v1/llm/router/models" -H "X-API-KEY: $B_API_KEY"
```

```json
{"object": "list", "data": [
  {"id": "my-fancy-llm-route", "object": "model", "created": 0, "owned_by": "router"}
]}
```

Jeder Eintrag in `data` ist ein Name, den man als `model` schicken kann. Nur
aktive Routen stehen hier; das Muster `provider/modell` steht nie darin.

### 2. Was steckt hinter einer Route?

```bash
curl -s "$B/api/v1/llm/router/routes" -H "X-API-KEY: $B_API_KEY"
```

```json
[{
  "id": "<id der Route>",
  "accountId": null,
  "logicalModel": "my-fancy-llm-route",
  "description": "Hello World",
  "enabled": true,
  "deployments": [
    {"id": "academiccloud-1", "providerId": "academiccloud", "upstreamModel": "gemma-4-31b-it",
     "priorityTier": 0, "weight": 3, "enabled": true},
    {"id": "academiccloud-2", "providerId": "openai", "upstreamModel": "ft:gpt-4o-2024-11-20",
     "priorityTier": 0, "weight": 1, "enabled": true},
    {"id": "academiccloud-3", "providerId": "academiccloud", "upstreamModel": "deepseek-v4-flash-0731",
     "priorityTier": 0, "weight": 1, "enabled": true}
  ],
  "maxAttempts": 1,
  "createdAt": "2026-09-30T13:03:51.535",
  "updatedAt": "2026-09-30T13:05:46.203"
}]
```

- `"accountId": null` — eine globale Route.
- Drei Modelle in Stufe 0 mit den Gewichten 3, 1 und 1: gemma bekommt etwa
  60 Prozent der Anfragen, die beiden anderen je etwa 20.
- Die Kennung ist nur ein Etikett: `academiccloud-2` ist hier ein OpenAI-Modell.
  Sprechende Kennungen erleichtern das Lesen von Logs und Fehlermeldungen.
- Zeitstempel sind UTC, auch ohne angehängtes „Z".
- Die `id` einer eigenen Route braucht man zum Ändern und Löschen.

### 3. Ein Modell ohne Route ansprechen

```bash
curl -s "$B/api/v1/llm/router/chat/completions" \
  -H "X-API-KEY: $B_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-5.6-luna",
       "messages": [{"role": "user", "content": "Antworte nur mit OK."}],
       "max_completion_tokens": 200}'
```

```json
{
  "id": "chatcmpl-EUFFZioMaCNQMw5vxQwgH9Vj3JrSR",
  "object": "chat.completion",
  "created": 1790877169,
  "model": "gpt-5.6-luna",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
               "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 13, "completion_tokens": 4, "total_tokens": 17}
}
```

(gekürzt) Die Antwort hat das OpenAI-Format:

- `choices[0].message.content` ist der Text.
- `model` nennt das Modell, das geantwortet hat — ohne Provider-Präfix.
- `finish_reason: "stop"` heißt fertig; `"length"` heißt, das Token-Budget war
  aufgebraucht und der Text bricht ab.
- `usage` zählt die Tokens; `created` ist ein Unix-Zeitstempel.

GPT-5-Modelle brauchen `max_completion_tokens` statt `max_tokens` — mehr dazu
unter [Worauf man achten muss](#worauf-man-achten-muss).

### 4. Eine eigene Route anlegen

```bash
curl -s -X POST "$B/api/v1/llm/router/routes" \
  -H "X-API-KEY: $B_API_KEY" -H "Content-Type: application/json" \
  -d '{"logicalModel": "mein-chat",
       "description": "luna zuerst, nano als Reserve",
       "deployments": [
         {"id": "luna", "providerId": "openai", "upstreamModel": "gpt-5.6-luna", "priorityTier": 0, "weight": 1},
         {"id": "nano", "providerId": "openai", "upstreamModel": "gpt-5-nano", "priorityTier": 1, "weight": 1}
       ],
       "maxAttempts": 2}'
```

```json
{
  "id": "6abe9df358dbc8d00c8a36ae",
  "accountId": "<eure Konto-ID>",
  "logicalModel": "mein-chat",
  "description": "luna zuerst, nano als Reserve",
  "enabled": true,
  "deployments": [
    {"id": "luna", "providerId": "openai", "upstreamModel": "gpt-5.6-luna",
     "priorityTier": 0, "weight": 1, "enabled": true},
    {"id": "nano", "providerId": "openai", "upstreamModel": "gpt-5-nano",
     "priorityTier": 1, "weight": 1, "enabled": true}
  ],
  "maxAttempts": 2,
  "createdAt": "2026-10-01T17:52:51.060451197",
  "updatedAt": "2026-10-01T17:52:51.060474642"
}
```

- Pflicht sind `logicalModel` und mindestens ein Eintrag mit `id`,
  `providerId` und `upstreamModel`.
- Fehlt etwas, gilt: Stufe 0, Gewicht 1, aktiv. Ohne `maxAttempts` gilt der
  Standard der B-API.
- Die Route ist sofort nutzbar. Ihre `id` merken:
  `export ROUTE_ID=6abe9df358dbc8d00c8a36ae`
- Beide Modelle sind GPT-5-Modelle und verstehen dieselben Parameter — darauf
  kommt es an.
- Gibt es im Konto schon eine Route dieses Namens: 409.

### 5. Die Route nutzen

```bash
curl -s "$B/api/v1/llm/router/chat/completions" \
  -H "X-API-KEY: $B_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "mein-chat",
       "messages": [{"role": "user", "content": "Antworte nur mit OK."}],
       "max_completion_tokens": 200}'
```

Die Antwort sieht aus wie in Schritt 3. `"model": "gpt-5.6-luna"` zeigt, dass
der Eintrag aus Stufe 0 geantwortet hat. Antwortet luna nicht, kommt nano dran.

### 6. Die Route ändern

```bash
curl -s -X PUT "$B/api/v1/llm/router/routes/$ROUTE_ID" \
  -H "X-API-KEY: $B_API_KEY" -H "Content-Type: application/json" \
  -d '{"logicalModel": "mein-chat",
       "description": "nur luna, Reserve aus",
       "deployments": [
         {"id": "luna", "providerId": "openai", "upstreamModel": "gpt-5.6-luna", "priorityTier": 0, "weight": 1},
         {"id": "nano", "providerId": "openai", "upstreamModel": "gpt-5-nano", "priorityTier": 1, "weight": 1, "enabled": false}
       ],
       "maxAttempts": 2,
       "clearCache": true}'
```

Die Antwort ist die gespeicherte Route — mit derselben `id` und neuem
`updatedAt`.

- `PUT` **ersetzt** die ganze Route. Darum immer alle Felder und alle Einträge
  mitschicken, nicht nur die geänderten.
- `"clearCache": true` verwirft die gespeicherten Antworten dieser Route.
- Die Änderung wirkt sofort.

### 7. Die Route löschen

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
  "$B/api/v1/llm/router/routes/$ROUTE_ID" -H "X-API-KEY: $B_API_KEY"
```

Ausgabe: `200` — die Antwort selbst ist leer. Eine unbekannte `id` ergibt
`404`. Danach antwortet der Name sofort mit 400 „No route configured".

### 8. Am Cache vorbei fragen

```bash
curl -s "$B/api/v1/llm/router/chat/completions?ignore-caching=true" \
  -H "X-API-KEY: $B_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "mein-chat",
       "messages": [{"role": "user", "content": "Antworte nur mit OK."}],
       "max_completion_tokens": 200}'
```

Die Antwort kommt neu erzeugt, mit neuer `id`, und wird nicht gespeichert. Mit
`?clear-cache=true` wird sie neu erzeugt und ersetzt die gespeicherte.

## Fehlermeldungen

**Beim Nutzen**

| Status | Antwort | Bedeutung | Was tun |
|---|---|---|---|
| 400 | `{"error": "No route configured for model 'x'"}` | Name unbekannt, Route deaktiviert, oder ein Modellname ohne Provider-Präfix | Namen prüfen (`GET …/router/models`) oder `provider/modell` schicken |
| 400 | `{"error": {"message": "Unsupported parameter: 'max_tokens' …"}}` | die Parameter passen nicht zum Modell — die Meldung kommt vom Provider | Parameter an die Modellfamilie anpassen |
| 503 | `{"error": "Model pricing unavailable for 'x' - cannot enforce cost quota"}` | das Modell hat keinen Preis in der B-API, oft ein Tippfehler hinter `openai/…` | Modellnamen prüfen; nicht wiederholen |
| 503 | `{"error": "No deployment could serve model 'x' (no deployment left)"}` | kein aktiver oder erreichbarer Eintrag | Einträge prüfen; nur wiederholen, wenn ein kurzer Ausfall wahrscheinlich ist |
| 503 | `… attempts: luna:NOT_ELIGIBLE (HTTP 403)` | das Modell kann diesen Endpunkt nicht, etwa ein Chat-Modell an `embeddings` | passendes Modell wählen; nicht wiederholen |
| 401 | leer | Schlüssel fehlt oder ist falsch | Header prüfen |

**Beim Verwalten**

| Status | Antwort | Bedeutung |
|---|---|---|
| 400 | `{"error": "Deployment ids must be unique within a route group"}` | eine Kennung kommt doppelt vor |
| 400 | `{"error": "Unknown provider 'x' in deployment 'y'"}` | den Provider gibt es nicht |
| 400 | `{"deployments[0].weight": "must be greater than 0"}` | eine Feldprüfung; vorne steht das Feld |
| 409 | `{"error": "The account already has a route group for model 'x'"}` | der Name ist im Konto schon vergeben |
| 404 | leer | die `id` gibt es nicht |

Regelverstöße kommen als `{"error": "…"}`, Feldprüfungen als
`{"<feld>": "<meldung>"}`. Wer die Antworten maschinell liest, sollte beide
Formen erwarten.

## Worauf man achten muss

1. **Alle Modelle einer Route müssen dieselben Parameter verstehen.** Der
   Router reicht die Anfrage unverändert an das gewählte Modell weiter.
   GPT-5- und o-Modelle verlangen `max_completion_tokens` und lehnen eine
   `temperature` ungleich 1 ab; ältere Modelle wie gpt-4o, gemma oder deepseek
   nehmen `max_tokens`. Diese Familien nicht in einer Route mischen.
2. **Dasselbe gilt beim Austausch.** Wird eine Route von gemma auf ein
   GPT-5-Modell umgestellt, scheitern Anwendungen, die `max_tokens` schicken,
   ab sofort mit 400. Neue Modelle aus derselben Familie wählen — oder die
   Anwendungen vorher anpassen.
3. **Beim Anlegen wird nichts über das Modell geprüft** — weder ob es
   existiert, noch was es kann. Fehler zeigen sich erst beim ersten Aufruf.
   In der UI schlägt das Feld die Modelle des Providers vor; über die API
   wird jeder Name angenommen.
4. **Der Cache** liefert wortgleichen Anfragen die alte Antwort, und
   Routenänderungen leeren ihn nicht. Nach einem Modelltausch den Cache
   leeren.
5. **Bei 503 erst die Meldung lesen.** Fehlender Preis, kein aktiver Eintrag
   und ein ungeeignetes Modell kommen alle als 503; Wiederholen hilft dann
   nicht. Auch ein Tippfehler mit Provider-Präfix — `openai/mein-chatt` statt
   `mein-chat` — endet so, nicht als „unbekannte Route".
6. **Rechte:** Routen anlegen und ändern braucht das Recht
   `LLM_ROUTE_MANAGE`. Das Recht nur an Schlüssel für die Verwaltung vergeben,
   nicht an Schlüssel von Anwendungen.
7. **Mehrere Server:** Auf Staging wirkten alle Änderungen sofort. Ob das bei
   mehreren B-API-Instanzen auch gilt, ist offen.

Dazu kommen die Punkte unter
[Nicht korrekt oder anders als beschrieben](#nicht-korrekt-oder-anders-als-beschrieben).

## Bestehende Anwendungen umstellen

Eine Anwendung, die bisher `/api/v1/llm/openai/chat/completions` aufruft, ruft
künftig `/api/v1/llm/router/chat/completions` auf. Die Reihenfolge entscheidet,
ob dabei etwas ausfällt:

1. **Zuerst die Routen, dann die Anwendungen.** Wer nur die Adresse ändert und
   weiter `"model": "gpt-5.6-luna"` schickt, bekommt sofort 400 — solange es
   keine Route dieses Namens gibt.
2. **Zwei Wege ohne Ausfall:**
   - Routen anlegen, die genau so heißen wie die Modelle, die die Anwendungen
     heute schicken (Route `gpt-5.6-luna` → openai / gpt-5.6-luna). Dann reicht
     die neue Adresse. Später auf sprechende Namen wie `chat-standard` umziehen.
   - Die Anwendungen schicken `provider/modell`, etwa `openai/gpt-5.6-luna`.
     Das geht ohne Route und nutzt den bisherigen Cache weiter.
3. **Danach Modelle zentral tauschen** — innerhalb derselben Parameter-Familie
   und mit „Cache leeren".
4. **Routen nicht umbenennen oder löschen**, solange Anwendungen sie nutzen. Die
   Wirkung ist sofort.

## Häufige Fragen

Die Fragen kamen aus dem Team; die Antworten stützen sich auf die Messungen
vom 2026-10-01.

**Ist das live getestet — funktioniert es nachweislich?**
Ja, gegen Staging: Anfragen über Routen und über `provider/modell`, eigene
Routen anlegen, ändern und löschen, der Vorrang eigener Routen, das Ausweichen
auf die nächste Stufe, der Cache und seine Schalter. Was im Einzelnen
bestätigt ist, steht im Abschnitt „Auf einen Blick". Nicht geprüft sind die
gewichtete Verteilung und das Ausweichen nach einem echten Ausfall eines
Providers — dafür braucht es mehrere unterscheidbare Modelle.

**Was passiert, wenn wir bestehende Anwendungen auf `/router/` umstellen, ohne dass es eine Route gibt?**
Sie bekommen sofort `400 No route configured for model '…'`; einen Rückfall
auf den Provider gibt es nicht. Ein bloßer Modellname wie `gpt-5.6-luna` zählt
nicht als Muster. Also erst die Route anlegen, dann umstellen — oder die
Anwendung schickt `openai/gpt-5.6-luna`, das geht ohne Route. Der Weg ohne
Ausfall steht unter
[Bestehende Anwendungen umstellen](#bestehende-anwendungen-umstellen).

**Müssen wir bei der Umstellung auf Reihenfolge und Timing achten?**
Auf die Reihenfolge ja: Routen vor Anwendungen. Beim Timing kaum — auf Staging
wirkte jede Routenänderung sofort, ob Anlegen, Abschalten oder Löschen. Zwei
Dinge einplanen: Der Cache einer Route beginnt leer, die ersten Anfragen
kommen also nicht mehr aus dem bisherigen Provider-Cache. Und ob Änderungen
bei mehreren B-API-Instanzen ebenso sofort wirken, ist noch nicht geprüft.

**Können wir über eine globale Route neue Modelle ausliefern, ohne die ENV der Anwendungen zu ändern?**
Ja — wenn die Anwendungen einen Routennamen schicken, tauscht ein Admin das
Modell in der Route, und die Anwendungen merken nichts davon. Zwei
Bedingungen: Das neue Modell muss dieselben Anfrage-Parameter verstehen
(GPT-5-Modelle brauchen `max_completion_tokens`, gemma oder gpt-4o nehmen
`max_tokens`), sonst scheitern die Anwendungen sofort mit 400. Und beim
Speichern den Cache leeren, sonst bekommen wortgleiche Anfragen weiter
Antworten des alten Modells.

**Kann man jedes Modell eines Providers ansprechen?**
Ja, jedes, für das die B-API einen Preis hat: als `provider/modell` im Feld
`model` (die Adresse bleibt `/api/v1/llm/router/…`), über eine Route — und
genauso schon bisher direkt über `/api/v1/llm/openai/…`. Ein Modell ohne Preis
weist die B-API mit `503 Model pricing unavailable` ab, bevor der Provider
gefragt wird.

**Prüft der Router, ob ein Modell den Endpunkt überhaupt kann?**
Beim Anlegen nicht: Eine Route nimmt jedes Modell an, auch eines, das es nicht
gibt. Beim Aufruf schon: Ein Chat-Modell an `/router/embeddings` wurde
abgewiesen — allerdings mit `503 … NOT_ELIGIBLE` statt einer klaren 400.
Welches Modell zu welchem Endpunkt passt, muss man also selbst wissen.

**Missbrauch und Kosten: Wie leicht hängt jemand ein teures Modell ein, und sind globale Routen sicherer als persönliche?**
Die Antworten berühren die Sicherheit der B-API. Sie sind gesondert an das
B-API-Team gegangen und stehen nicht in diesem öffentlichen Dokument.

**Ersetzt das Routing die Modell-Einschränkung über Umgebungsvariablen?**
Teilweise. Routen legen zentral fest, welches Modell eine Anwendung bekommt —
das ersetzt die Modellnamen in der ENV. Eine Grenze für den Schlüssel sind sie
nicht: Wer ihn hat, erreicht jedes bepreiste Modell der freigegebenen Provider
auch direkt. Nachhaltig wäre eine Freigabeliste von Modellen je Konto in der
B-API.

## Aus Python

Der edu-sharing-python-client — dieses Repositorium — kann den Router ab
Version 0.3.6; die Einzelheiten stehen im
[README](../README.de.md#der-router--modellgruppen-die-auf-dem-gateway-liegen):

```python
from edusharing.bapi import BildungsAPI

# in einer async-Funktion; liest B_API_KEY und B_API_BASE_URL
async with BildungsAPI.from_env(provider="router") as api:
    text = await api.chat("Fasse zusammen: …", model="mein-chat")
    print(api.last_model)          # das Modell, das geantwortet hat
    routen = await api.routes()    # eigene und globale Routen
```

Die Bibliothek baut die Anfrage passend zu den Modellen hinter einer Route.
Nach einem Modelltausch passt sie sich also selbst an (Punkt 2 unter „Worauf
man achten muss"), und eine gemischte Route (Punkt 1) lehnt sie ab, bevor etwas
gesendet wird. Routen anlegen, ändern und löschen geht mit `create_route`,
`replace_route` und `delete_route`; `gateway_cache=False` fragt am Cache
vorbei.

**Gemischte Modelle bündelt die Bibliothek selbst.** Eine Route ersetzt die
Gruppen der Bibliothek (`virtual_models`) nicht: Am Router darf eine Gruppe
`provider/modell` verschiedener Provider nennen, die Bibliothek versucht sie
in der geschriebenen Reihenfolge und baut für jedes Modell die passende
Anfrage — auch für GPT-5 und gemma in einer Gruppe, was eine Route nicht kann:

```python
text = await api.chat("Fasse zusammen: …",
                      model=["openai/gpt-5.6-luna", "academiccloud/gemma-4-31b-it"])
```

Faustregel: eine Route, wo viele Anwendungen einen Namen teilen, der zentral
geändert wird (Modelle einer Art); eine Gruppe in der Bibliothek, wo Modelle
verschiedener Art zusammenkommen oder die Auslastung der AcademicCloud
entscheiden soll. Das Beispiel
[`28_bapi_bundling.py`](examples/28_bapi_bundling.py) zeigt beides.

## Noch offen

- Was `maxAttempts` genau zählt: Aufrufe je Anfrage oder je Modell.
- Wie lange der Cache Antworten hält.
- Ob Änderungen auch bei mehreren B-API-Instanzen sofort wirken.
- Fragen zu Rechten und Kosten — gesondert beim B-API-Team.

Vorschläge zu den einzelnen Befunden stehen in der Tabelle
[Nicht korrekt oder anders als beschrieben](#nicht-korrekt-oder-anders-als-beschrieben),
Messungen und Belege im [Testbericht vom 2026-10-01](audits/2026-10-01-bapi-router.md).

## Was gegenüber der ersten Fassung präzisiert wurde

Die erste Fassung ist die Beschreibung, mit der das B-API-Team das Routing
vorgestellt hat.

- **Gewichte** sind ganze Zahlen ab 1, relativ innerhalb einer Stufe — 50/50
  heißt 1 und 1, nicht 0,5.
- **„Die Modelle müssen die Funktion unterstützen"** reicht nicht: Sie müssen
  auch dieselben Anfrage-Parameter verstehen.
- **Tippfehler mit Provider-Präfix** enden mit 503 „Model pricing
  unavailable", nicht mit „unbekannte Route".
- **Der Cache** gilt auch für direkte Provider-Aufrufe, überlebt
  Routenänderungen und lässt sich je Anfrage umgehen.
- **Max. Versuche:** Die API-Beschreibung spricht von Aufrufen je Anfrage, die
  erste Fassung von Versuchen je Modell — noch offen.
- **Neu:** die Übersicht, was geprüft und bestätigt ist und was nicht korrekt
  funktioniert hat; die Zuordnung von UI und API; wer welche Routen sieht; die
  Endpunkte; Beispielaufrufe mit Antworten; die Fehlermeldungen; Grenzen; der
  Weg zur Umstellung; die häufigen Fragen aus dem Team und die Nutzung aus
  Python. Die Verweise auf Bilder sind durch Text ersetzt.
