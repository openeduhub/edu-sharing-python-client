# Testbericht: LLM-Routing der B-API

Gemessen am 2026-10-01 gegen Staging. **Öffentliche Fassung:** Die Antwort auf
die Team-Frage nach Missbrauch und Kosten (Frage 4) berührt die Sicherheit der
B-API und ist gesondert an das B-API-Team gegangen. Die Nutzungsanleitung, die
auf diesen Messungen aufbaut, steht in
[`docs/B-API-ROUTING.de.md`](../B-API-ROUTING.de.md).

## Ergebnis in Kürze

- **Die Funktion arbeitet in ihren Kernpunkten wie beschrieben** — live
  nachgewiesen gegen Staging: das Muster `provider/modell`, eigene Routen
  anlegen, nutzen, ändern und löschen, der Vorrang eigener vor globalen
  Routen, das Umschalten an einem nicht nutzbaren Deployment vorbei, Cache und
  Cache-Schalter. Routenänderungen wirken sofort.
- **13 Abweichungen und Auffälligkeiten** (B1–B13). Die drei mit der größten
  Wirkung: der Anfragekörper geht unverändert an jedes Deployment, sodass eine
  Route nur Modelle mit denselben Parametern bündeln kann (B1); Antworten
  kommen auch bei den Provider-Routen ungekennzeichnet aus einem Cache (B4);
  dauerhafte Fehler melden sich als 503 und laden zum vergeblichen Wiederholen
  ein (B6, B7, B12).
- **Fragen aus dem Team**: Umstellung nur in der Reihenfolge „erst Routen, dann
  Apps" — eine App, die nur die URL ändert, bekommt sofort 400. Erreichbar ist
  jedes Modell, für das die B-API einen Preis hat; ob ein Modell zum Endpunkt
  passt, prüft der Router erst beim Aufruf und meldet einen Fehlgriff als 503.
  Frage 4 ist gesondert beantwortet.
- **Die Bibliothek ist angepasst** (`edu-sharing-python-client` ab
  [`v0.3.6`](https://github.com/openeduhub/edu-sharing-python-client/tree/v0.3.6)):
  `provider="router"`, ein Anfragekörper je Route, Routenverwaltung,
  `last_model` nach Router-Antworten, `gateway_cache=False`, Gruppen über
  Provider am Router.

## Rahmen

| | |
|---|---|
| Instanz | `https://b-api.staging.openeduhub.net` |
| Datum | 2026-10-01, ca. 12:10–13:20 UTC |
| Konto | eigener API-Schlüssel (aus `.env`, nie ausgegeben); hat das Recht `LLM_ROUTE_MANAGE` |
| Erzeugende Aufrufe | nur `openai` / `gpt-5.6-luna` (Vorgabe); ein zweites Deployment nennt ein **nicht existierendes** Modell und kann nur scheitern |
| Testdaten | Wegwerf-Routen `es-client-probe-*` im eigenen Konto, alle wieder gelöscht, Löschung jeweils durch erneutes Auflisten geprüft |
| Globale Routen | nur gelesen, nie geändert |
| Skripte | eigene Prüfskripte, nicht veröffentlicht; jede Zahl unten stammt aus einem ihrer Läufe. Die Kernpunkte prüfen die Live-Tests der Bibliothek nach (siehe [Anhang](#anhang-nachprüfen)) |

## Befunde zur Funktion (Server)

### Was wie beschrieben funktioniert

| # | Prüfung | Ergebnis |
|---|---|---|
| S1 | Muster `openai/gpt-5.6-luna` über `/router/chat/completions` | 200 in 1,86 s, Antwort `model: "gpt-5.6-luna"` |
| S2 | `responses` über das Muster | 200, `status: completed` |
| S3 | `GET /api/v1/llm/provider` | listet `academiccloud`, `openai` **und `router`** |
| S4 | `GET /router/models` | nur Routen (`owned_by: "router"`, `created: 0`), das Muster erscheint nicht |
| S5 | Unbekannter Name, unbekannter Provider-Präfix | 400 `{"error": "No route configured for model '…'"}` |
| S6 | Eigene Route anlegen / ersetzen / löschen | POST 200, PUT 200 (id bleibt, `updatedAt` neu), DELETE 200; gelöschte Route antwortet sofort 400 |
| S7 | Eigene **aktive** Route mit dem Namen der globalen `my-fancy-llm-route` | die eigene antwortet (luna statt gemma/gpt-4o/deepseek) |
| S8 | Eigene **deaktivierte** Route gleichen Namens | `/routes` listet eigene (deaktiviert) und globale |
| S9 | Route mit Namen in Musterform (`openai/es-client-probe-…`) | die Route gewinnt vor dem Muster |
| S10 | Deaktivierte Route | nicht in `/models`, Chat 400 „No route configured" |
| S11 | Provider-Cache: wortgleiche Anfrage an `/openai/chat/completions` | zweite Antwort in 0,05 s, gleiche `id` |
| S12 | Muster teilt sich den Provider-Cache | über `/router/…` dieselbe `id` wie vorher direkt beim Provider |
| S13 | Routen-Cache | zweite Antwort in 0,06 s, gleiche `id` |
| S14 | `ignore-caching=true` | neue Antwort, **nicht** gespeichert (danach kam wieder die alte) |
| S15 | `clear-cache=true` | neue Antwort, **ersetzt** den Eintrag (danach kommt die neue) |
| S16 | Auth | ohne Schlüssel 401, falscher Schlüssel 401, `Authorization: Bearer` 200 |
| S17 | Standardwerte beim Anlegen | ohne `priorityTier`/`weight`/`enabled`: 0 / 1 / true; ohne `maxAttempts`: `null` |
| S18 | Routenänderungen | wirken sofort: neu angelegt sofort nutzbar, Deployment aus → sofort 503, wieder an → sofort 200, gelöscht → sofort 400 (T2, T4, S6) |
| S19 | Routen-Cache und Provider-Cache | getrennt: dieselbe Frage erst beim Provider, dann über eine Route ergab eine neue Antwort (T3) |
| S20 | Cache nach einer Routenänderung | überlebt sie (gleiche `id` nach PUT); `clearCache: true` beim PUT leert ihn (T4) — wie der Hinweis in der UI sagt |

### Abweichungen und Auffälligkeiten

**B1 — Der Anfragekörper wird unverändert durchgereicht, auch bei Routen.**
Der Körper mit `max_tokens` an eine Route, deren einziges Deployment
`gpt-5.6-luna` ist, endet mit OpenAIs eigenem 400 *„Unsupported parameter:
'max_tokens' is not supported with this model. Use 'max_completion_tokens'
instead."* — ebenso über das Muster. Folge: Alle Deployments einer Route
müssen nicht nur dieselbe *Funktion* unterstützen (so die Doku), sondern
dieselben *Parameter*. GPT-5- und o-Modelle verlangen `max_completion_tokens`
und lehnen eine `temperature` ≠ 1 ab; ältere und die AcademicCloud-Modelle
nehmen `max_tokens`. Eine Route, die beide Familien mischt, kann mit keinem
einzelnen Körper alle Deployments bedienen. **Vorschlag:** in der Doku
ergänzen; langfristig Parameter je Deployment anpassen oder eine
Fehlermeldung beim Anlegen.

**B2 — `maxAttempts`: Doku und Spec sagen Verschiedenes.** Die Doku: „wie
viele Versuche die Route macht ein Modell zu erreichen, bevor das nächste
Modell angesprochen wird" (je Modell). Die Spec: „Overrides the global maximum
number of upstream calls per request" (je Anfrage, insgesamt). Gemessen: Route
mit Stufe 0 = Modell ohne Preis, Stufe 1 = luna, `maxAttempts: 1` → 200 von
luna. Das passt zu keiner der beiden Lesarten sauber — oder die Preisprüfung
zählt nicht als Versuch. Die globale `my-fancy-llm-route` steht auf
`maxAttempts: 1`; nach der Spec-Lesart schaltet sie nach einem echten
Upstream-Fehler nie auf ein anderes Deployment um. **Vorschlag:** Semantik
festlegen und an beiden Stellen gleich beschreiben.

**B3 — Gewichte sind Ganzzahlen > 0.** Die Doku schlägt „0,5 einstellen →
50/50" vor. `weight` ist `int32`, und der Server lehnt 0 ab
(`{"deployments[0].weight": "must be greater than 0"}`); 50/50 heißt gleiche
Gewichte, z. B. 1 und 1. Die Spec nennt `minimum: 0` — **Spec ≠ Server**.

**B4 — Gecachte Antworten sind nicht zu erkennen.** Keine Kopfzeile kennzeichnet
einen Treffer (es kommen nur `content-type`, `content-security-policy`,
`content-encoding`), und `id`, `created` und `usage` sind die der ersten
Antwort. Ein Client kann frisch und gecacht nicht unterscheiden; ob ein
Treffer Kontingent oder Kosten zählt, ist von außen nicht zu sehen. Der Cache
greift **auch auf den Provider-Routen** (`/api/v1/llm/openai/…`), nicht nur
beim Router — wer zweimal dasselbe fragt, bekommt dieselbe Antwort, egal mit
welcher Erwartung. **Vorschlag:** `X-Cache: HIT|MISS`; Cache-Schlüssel und
Lebensdauer dokumentieren.

**B5 — Welches Deployment geantwortet hat, ist nicht zu sehen.** Nur das Feld
`model` der Antwort nennt das Upstream-Modell — ohne Provider, ohne
Deployment-Kennung. Nutzen zwei Deployments dasselbe Modell (oder dasselbe
Modell bei zwei Providern), sind Gewichtung und Umschalten von außen nicht
nachprüfbar, obwohl die Kennung laut Doku genau dafür vergeben wird.
**Vorschlag:** Kopfzeilen wie `X-Route` und `X-Route-Deployment`.

**B6 — Ein Tippfehler mit Provider-Präfix endet mit 503, nicht 400.**
`openai/<Routenname>` geht wie in der Doku beschrieben an OpenAI, antwortet
aber `503 Model pricing unavailable for '…' - cannot enforce cost quota`. 503
heißt „später nochmal", der Zustand ist aber dauerhaft — Clients mit
Wiederholungslogik warten umsonst (die Bibliothek hat dafür eine Ausnahme,
gemessen 15 s statt 0,1 s, bevor es sie gab).

**B7 — Route ohne aktives Deployment: gelistet, aber 503.** Eine aktive Route,
deren Deployments alle deaktiviert sind, steht in `/models`; ein Aufruf endet
mit `503 {"error": "No deployment could serve model '…' (no deployment
left)"}`. Dieselbe Meldung ist vermutlich auch die Antwort, wenn alle
Deployments vorübergehend als unerreichbar gemerkt sind — ein Client kann
„dauerhaft falsch konfiguriert" nicht von „gleich wieder da" unterscheiden.
**Vorschlag:** solche Routen nicht listen; beim Konfigurationsfall 400/409,
beim vorübergehenden Fall 503 mit `Retry-After`.

**B8 — Nicht dokumentierte Statuscodes.** Doppelter Routenname im Konto →
**409** `{"error": "The account already has a route group for model '…'"}`;
PUT/DELETE mit unbekannter id → **404 mit leerem Körper**. Die Spec nennt für
diese Operationen nur 200, 400, 401 und 504.

**B9 — Zwei Fehlerformen.** Regelverstöße kommen als `{"error": "…"}`,
Feldprüfungen als `{"<feld>": "<meldung>"}` (z. B.
`{"maxAttempts": "must be less than or equal to 10"}`). Ein Client muss beide
lesen können. Die Spec deutet das mit `oneOf` an.

**B10 — Zeitstempel ohne Zeitzone.** `createdAt`/`updatedAt` kommen als
`"2026-10-01T12:17:23.076453464"` — ohne Offset, mit Nanosekunden. Die Werte
sind UTC (abgeglichen mit `created` einer Chat-Antwort drei Sekunden später),
aber nicht so gekennzeichnet. Spec: `format: date-time` (RFC 3339 verlangt den
Offset), das Swagger-Beispiel zeigt `…Z`.

**B11 — Kleinigkeiten in der Spec.** `LlmRouteGroupRequest.accountId` sagt
„leave empty for a global group" — für den Konto-Endpunkt irreführend, dort
wird eine leere `accountId` dem eigenen Konto zugeordnet. `DELETE` antwortet
200 ohne Körper (kein 204).

**B12 — Ein Modell am falschen Endpunkt meldet sich als 503.**
`/router/embeddings` mit dem Chat-Modell `gpt-5.6-luna` — als Muster wie über
eine Route — endete mit `503 {"error": "No deployment could serve model … (no
deployment left); attempts: provider-prefix:NOT_ELIGIBLE (HTTP 403)"}` (T5).
Durch kommt nichts, aber ein dauerhafter Fehler sieht aus wie ein
vorübergehender. Woran die Eignung gemessen wird, ist von außen nicht zu
sehen. **Vorschlag:** 400 mit klarer Meldung.

**B13 — Beim Anlegen einer Route wird das Modell nicht geprüft.** Ein nicht
existierender Modellname wurde angenommen (S6). Geprüft wird nur, ob der
Provider existiert. Ein Tippfehler im Modellnamen fällt erst beim ersten
Aufruf auf — und dann als 503 (B6).

### Validierung beim Anlegen (alle korrekt abgelehnt, nichts angelegt)

| Eingabe | Antwort |
|---|---|
| doppelte Deployment-Kennung | 400 `{"error": "Deployment ids must be unique within a route group"}` |
| unbekannter Provider | 400 `{"error": "Unknown provider 'nosuchprovider' in deployment 'x'"}` |
| `weight: 0` | 400 `{"deployments[0].weight": "must be greater than 0"}` |
| `maxAttempts: 0` / `11` | 400 `… greater than or equal to 1` / `… less than or equal to 10` |
| keine Deployments | 400 `{"deployments": "must not be empty"}` |
| leerer Name | 400 `{"logicalModel": "must not be blank"}` |
| `priorityTier: -1` | 400 `… must be greater than or equal to 0` |

## Nicht getestet — und warum

| Was | Warum nicht |
|---|---|
| Gewichtete Verteilung, Umschalten nach echtem Upstream-Fehler | braucht unterscheidbare Deployments, also andere Modelle als luna (Vorgabe); und B5: die Antwort sagt nicht, welches Deployment es war |
| Andere Routen über den Router mit passenden Modellen (`embeddings`, `audio/*`, `images/*`, `moderations`) | andere Modelle; gemessen ist nur der Fehlfall „Chat-Modell an `embeddings`" (B12) |
| Mischrouten GPT-5 + ältere Modelle: nimmt die AcademicCloud `max_completion_tokens`? | andere Modelle; die Bibliothek lehnt solche Routen deshalb vorerst ab (L2) |
| Administrations-Endpunkte (`/administration/llm-routing/*`) | Admin-Recht |
| Gemerkte Unerreichbarkeit, `providerPrefixFallback=false`, Last und Ratenlimits | nicht von außen steuerbar bzw. außerhalb des Auftrags |
| Fragen zu Rechten und Kosten | nicht Teil dieser öffentlichen Fassung; gesondert an das B-API-Team |

## Fragen aus dem Team

Gemessen mit eigenen Prüfskripten (Wegwerf-Routen, nur luna, danach alles
gelöscht und nachgeprüft).

### 1. Live getestet — ist nachgewiesen, dass es funktioniert?

Ja, gegen Staging am 2026-10-01: das Muster `provider/modell` (S1, S2), eigene
Routen anlegen, nutzen, ändern und löschen (S6), der Vorrang eigener vor
globalen Routen (S7, S9), Umschalten an einem nicht nutzbaren Deployment
vorbei (B2), Cache und Cache-Schalter (S11–S15). Nicht nachweisbar mit nur
einem Modell: die gewichtete Verteilung und das Umschalten nach einem echten
Upstream-Fehler (siehe „Nicht getestet").

### 2. Was passiert, wenn bestehende Zugriffe ohne konfigurierte Route auf `/router/` umgestellt werden — Reihenfolge und Timing?

| # | Messung | Ergebnis |
|---|---|---|
| T1 | App stellt nur die URL um, schickt weiter `model: "gpt-5.6-luna"`, keine Route | **sofort 400** `{"error": "No route configured for model 'gpt-5.6-luna'"}` |
| T2 | Route anlegen, die **genau wie das Modell heißt** (`gpt-5.6-luna` → openai/gpt-5.6-luna), dieselbe unveränderte Anfrage | **200**, direkt nach dem Anlegen |
| S1 | Statt einer Route das Muster `openai/gpt-5.6-luna` als `model` | 200 ohne jede Route |
| T3 | Dieselbe Frage erst direkt beim Provider, dann über eine Route | **eigener Cache**: neue Antwort (andere `id`, 1,4 s). Das Muster dagegen teilt den Provider-Cache (S12) |
| T4 | Route ändern (anderes Deployment, gleiches Modell) ohne `clearCache` | Änderung greift, aber die **alte Antwort kommt aus dem Cache** (0,11 s, gleiche `id`) |
| T4 | dieselbe Änderung mit `clearCache: true` | neue Antwort |
| T4 | Deployment deaktivieren / wieder aktivieren | **sofort** 503 „no deployment left" / **sofort** wieder 200 |
| S6 | Route löschen | **sofort** 400 „No route configured" |

**Folgerung für die Umstellung:**

1. **Erst die Routen, dann die Apps.** Eine App, die nur die URL auf
   `/router/` umstellt, bricht sofort mit 400 ab, solange es keine Route mit
   dem gesendeten Namen gibt (T1). Kein Rückfall auf den Provider.
2. **Zwei sichere Wege ohne Ausfall:** (a) globale Routen anlegen, die exakt so
   heißen wie die Modell-IDs, die die Apps heute schicken — dann reicht die
   URL-Umstellung (T2); später auf sprechende Routennamen umziehen. Oder (b) die
   Apps schicken `provider/modell` (z. B. `openai/gpt-5.6-luna`) — das geht
   ganz ohne Route und teilt sich den bisherigen Cache (S1, S12). Wichtig bei
   (b): `<provider>/<routenname>` ist ein Tippfehler-Risiko (B6).
3. **Timing:** Routenänderungen wirkten auf Staging ohne Verzögerung (T2, T4,
   S6). Ob das bei mehreren Gateway-Instanzen auch gilt, ist offen — es gibt
   einen Admin-Endpunkt `POST /administration/llm-routing/reload`, der auf
   einen Zwischenspeicher hindeutet (nicht getestet).
4. **Routen nie entfernen oder umbenennen, solange Apps sie nutzen** — die
   Wirkung ist sofort (S6, S10).
5. **Der Cache beginnt nach der Umstellung auf eine Route kalt** (T3), und er
   **überlebt Änderungen an der Route** (T4): wer ein Modell tauscht, sollte
   `clearCache` setzen (in der UI der Schalter „Cache dieser Route beim
   Speichern leeren"), sonst liefern wortgleiche Anfragen weiter die Antworten
   des alten Modells.
6. **„Neue Modelle ohne ENV-Änderung ausliefern" geht nur innerhalb einer
   Parameter-Familie.** Der Router reicht den Körper unverändert durch (B1).
   Wird eine Route z. B. von `gemma-4-31b-it` auf `gpt-5.6-luna` umgestellt,
   schicken die Apps weiter `max_tokens`/`temperature` und bekommen ab sofort
   400 (gemessen mit genau diesem Körper an einer luna-Route). Umgekehrt
   genauso, wenn Apps für GPT-5 `max_completion_tokens` schicken und das neue
   Modell das nicht kennt (nicht gemessen). Apps mit der Bibliothek passen den
   Körper selbst an — mit bis zu 30 s Verzögerung, solange ihre Routenliste
   gemerkt ist.

### 3. Kann man alle Modelle des Providers ansprechen? Prüft der Router, was ein Modell kann?

- **Erreichbar ist jedes Modell, für das die B-API einen Preis hat** — über das
  Muster im Feld `model` (nicht im URL-Pfad: der bleibt
  `/api/v1/llm/router/chat/completions`), über eine Route, und genauso schon
  heute direkt über `/api/v1/llm/openai/…`. Ein Modell ohne Preis wird vor dem
  Provider abgewiesen: `503 Model pricing unavailable` (gemessen mit einem
  nicht existierenden Namen; dieselbe Antwort kam am 2026-09-21 für gelistete,
  aber nicht abgerechnete Modelle wie `dall-e-3`).
- **Beim Anlegen einer Route wird das Modell nicht geprüft**: ein nicht
  existierender Modellname wurde angenommen (S6). Geprüft wird nur, ob der
  Provider existiert (Validierungstabelle).
- **Beim Aufruf greift eine Prüfung, aber mit irreführendem Status (T5):**
  `/router/embeddings` mit dem Chat-Modell `gpt-5.6-luna` — als Muster wie als
  Route — endete mit **503** `"No deployment could serve model … (no deployment
  left); attempts: provider-prefix:NOT_ELIGIBLE (HTTP 403)"`. Es kommt also
  nichts durch, aber ein dauerhafter Fehler (falsches Modell für den Endpunkt)
  meldet sich als „vorübergehend nicht verfügbar"; Clients mit
  Wiederholungslogik warten umsonst. **Vorschlag:** 400 mit klarer Meldung
  („model … is not eligible for /embeddings"). Woran die Eignung gemessen wird
  (Preis je Endpunkt? Modell-Metadaten?), ist von außen nicht zu sehen.

### 4. Wie hoch ist die Hürde, böswillig ein teures Modell einzuhängen — und sind globale Routen sicherer als persönliche?

Die Antwort berührt die Sicherheit der B-API. Sie ist gesondert an das
B-API-Team gegangen und steht nicht in dieser öffentlichen Fassung.

## Bibliothek (edu-sharing-python-client): Befunde und Anpassung

### Was die Tests an der Bibliothek gezeigt haben

| # | Befund | Folge |
|---|---|---|
| L1 | `provider="router"` baute schon die richtigen Pfade — die Bibliothek kennt keine feste Provider-Liste | genutzt, nichts geändert |
| L2 | Der Anfragekörper richtete sich nach dem Präfix der Modell-ID; `openai/gpt-5.6-luna` und Routennamen galten als „unbekannte Familie" → `max_tokens` + `temperature` → **gemessen 400** an luna | **behoben**: Körper für die Modelle hinter dem Namen |
| L3 | `respond()` ließ für solche Namen die Vorgabe `reasoning_effort=low` fallen und lehnte einen ausdrücklichen Wert ab | **behoben**, gleiche Regel wie `chat()` |
| L4 | Der Gateway-Cache (B4) war der Bibliothek unbekannt — weder dokumentiert noch abschaltbar | **behoben**: dokumentiert, `gateway_cache=False` |
| L5 | `last_model` hätte den Routennamen genannt, nicht das Modell, das antwortete | **behoben**: bei Router-Antworten das Feld `model` der Antwort |
| L6 | DELETE antwortet 200 ohne Körper; ein Fehler ohne Körper endete in einer Meldung mit Doppelpunkt am Ende | **behoben**: als Bytes gelesen; „(the gateway sent no message)" |
| L7 | Ein Test-Docstring behauptete „Bearer ergibt 401" (gemessen 200); im englischen Skill stand ein deutscher Halbsatz | **behoben** |
| L8 | OpenAI listet `gpt-6-luna`; die Familienpräfixe der Bibliothek kennen nur `gpt-5`, `o1`, `o3`, `o4` — ein GPT-6-Modell bekäme den älteren Körper | **offen**: braucht eine Messung mit gpt-6 (außerhalb der Vorgabe „nur luna") |
| L9 | 503 „no deployment left" (B7, B12) wiederholt die Bibliothek wie jede 503 — begrenzt, bei Standardwerten rund 17 s | **offen, bewusst**: dieselbe Meldung kann auch einen vorübergehenden Ausfall bedeuten, und den konnte ich nicht messen |
| L10 | Die Routenliste wird 30 s gemerkt: stellt ein Admin eine Route auf eine andere Modellfamilie um, baut die Bibliothek bis zu 30 s lang den alten Körper | dokumentiert; `models_cache_seconds=0` vermeidet es um den Preis einer Anfrage je Aufruf |

### Was sich geändert hat (Version 0.3.6)

- **Router als Provider:** `BildungsAPI(provider="router")` oder
  `chat(..., provider="router")`; `model` ist ein Routenname oder
  `provider/modell`.
- **Ein Körper je Route:** `chat` und `respond` lesen die Routenliste und
  bauen den Körper für die Modelle dahinter — in der Reihenfolge des Gateways
  (eigene aktive Route, dann globale aktive, dann das Muster). Optionales nur,
  wo jedes Modell es nimmt; eine Route aus GPT-5- und älteren Modellen wird vor
  dem Senden mit `ValidationError` abgelehnt.
- **Routenverwaltung:** `routes()`, `create_route()`, `replace_route()`,
  `delete_route()`, Werte `Route` und `Deployment`. Anlegen und Löschen werden
  nach einem Fehlschlag, der schon gewirkt haben kann, nicht wiederholt.
- **Cache:** `BildungsAPI(gateway_cache=False)` schickt `ignore-caching=true`
  bei jeder durchgereichten Anfrage; `replace_route(…, clear_cache=True)` leert
  den Cache einer Route.
- **Gruppen über Provider am Router:** `model=["openai/gpt-5.6-luna",
  "academiccloud/…"]` — die Bibliothek versucht die Mitglieder in der
  geschriebenen Reihenfolge und baut jedem den Körper seiner Familie; genau
  das kann eine Route nicht (B1).
- **Doku** in beiden Sprachen (README, REFERENCE, ARCHITECTURE, Skill,
  TRAPS 2.17, CHANGELOG) und die Beispiele
  [`27_bapi_router.py`](../examples/27_bapi_router.py) und
  [`28_bapi_bundling.py`](../examples/28_bapi_bundling.py).
- `virtual_models` bleibt: es rankt nach Auslastung, die der Router nicht
  nutzt, baut jedem Modell einen eigenen Körper und funktioniert an jedem
  Gateway.

### Verifikation

| Prüfung | Ergebnis |
|---|---|
| Offline-Suite | 3059 bestanden, 12 übersprungen; `ruff` und `mypy` ohne Befund (Release 0.3.6) |
| Router-Tests offline | 91 in `tests/test_bapi_router.py`, 7 für Beispiel 28; `router.py` zu 100 % abgedeckt, Zweige eingeschlossen |
| Mutationsprüfung | 47 absichtlich eingebaute Fehler über fünf Commits, alle von den Tests gefangen; wo einer zunächst durchrutschte, wurde der Test nachgeschärft |
| Live gegen Staging | `tests/test_live_bapi_router.py`: 5 bestanden (Muster, unbekannte Route, Cache an/aus, Route vom Anlegen bis zum Löschen, Gruppe über Provider), zuletzt auf dem Stand von `v0.3.6` |
| Beispiele live | 27 und 28: Exit 0 auf dem Stand von `v0.3.6` |
| Aufräumen | nach jedem Lauf nur noch die globale `my-fancy-llm-route` vorhanden |
| CI (GitHub) | `v0.3.6`: Python 3.11–3.14 unter Linux, 3.13 unter Windows, Mindestversionen, Neugenerierung, Abdeckung, Paket — und CodeQL grün |

## Empfehlungen an das B-API-Team (gesammelt)

| # | Empfehlung | Befund |
|---|---|---|
| E1 | Doku: alle Deployments einer Route brauchen dieselben **Anfrageparameter**, nicht nur dieselbe Funktion; GPT-5/o vs. ältere Modelle nennen | B1 |
| E2 | `maxAttempts` eindeutig beschreiben (je Anfrage oder je Modell? zählt die Preisprüfung?) — Doku und Spec angleichen | B2 |
| E3 | Gewichte als ganze Zahlen > 0 dokumentieren (statt „0,5"); Spec `minimum: 1` | B3 |
| E4 | Gecachte Antworten kennzeichnen (`X-Cache: HIT/MISS`); Cache-Schlüssel und -Dauer dokumentieren, auch für die Provider-Routen | B4 |
| E5 | Antwortende Route und Deployment als Kopfzeilen (`X-Route`, `X-Route-Deployment`) | B5 |
| E6 | Dauerhafte Fehler als 400 statt 503: unbekanntes/unbepreistes Modell, keine aktive Deployment-Konfiguration, Modell ungeeignet für den Endpunkt; 503 nur für Vorübergehendes, dann mit `Retry-After` | B6, B7, B12 |
| E7 | Routen ohne aktives Deployment nicht in `/models` listen | B7 |
| E8 | Spec: 404 und 409 für die Routen-Endpunkte ergänzen; Zeitstempel mit Zeitzone (`Z`) | B8, B10 |
| E9 | Beim Anlegen das Modell prüfen (existiert es, hat es einen Preis?) — wenigstens als Warnung | B13 |
| E10 | Sicherheit: gesondert an das B-API-Team | Team-Frage 4 |
| E11 | Für die Umstellung: Routen vor den Apps anlegen; beim Modelltausch `clearCache` setzen; Modelltausch nur innerhalb einer Parameter-Familie | Team-Frage 2 |

## Anhang: Nachprüfen

Die Prüfskripte sind nicht veröffentlicht. Die Kernpunkte prüfen die
Live-Tests der Bibliothek nach —
[`tests/test_live_bapi_router.py`](../../tests/test_live_bapi_router.py) — und
die Beispiele [`27_bapi_router.py`](../examples/27_bapi_router.py) und
[`28_bapi_bundling.py`](../examples/28_bapi_bundling.py):

```bash
B_API_KEY=... B_API_BASE_URL=https://b-api.staging.openeduhub.net \
  uv run pytest -m "live or write" tests/test_live_bapi_router.py
```

Sie fragen `gpt-5.6-luna`; andere Modelle stehen nur als Reserve dahinter, für
den Fall, dass luna nicht antwortet. Was sie anlegen, löschen sie wieder, und
der Lauf prüft am Ende, dass keine Spur bleibt.
