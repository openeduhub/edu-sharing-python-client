# Design: Das Routing der B-API

## Ziel

`BildungsAPI` kann den Router der B-API benutzen: einen Routennamen (oder
`provider/modell`) als `model` schicken, einen Anfragekörper bekommen, der zu
den Modellen hinter der Route passt, die Routen des eigenen Kontos verwalten
und den Antwort-Cache des Gateways umgehen.

## Kontext

Die B-API bündelt seit Ende September Modelle mehrerer Provider zu Routen
(`/api/v1/llm/router/…`). Das ist die serverseitige Form dessen, was die
Bibliothek mit `virtual_models` clientseitig tut. Gemessen am 2026-10-01 gegen
Staging (Testbericht: `b-api-test/TESTBERICHT-ROUTING-2026-10-01.md`):

| Befund | Folge für die Bibliothek |
|---|---|
| `GET /api/v1/llm/provider` führt `router` als Provider; alle Pfade sind `/api/v1/llm/router/{route}` | `provider="router"` baut schon heute die richtigen Pfade |
| Der Router reicht den Körper **unverändert** durch — bei Routen und beim Muster | `max_tokens` an eine luna-Route: OpenAIs 400. Der Körper muss zu den Modellen **hinter** dem Namen passen |
| Die Körperform hängt heute am Präfix der Modell-ID | `openai/gpt-5.6-luna` und Routennamen werden nicht als GPT-5 erkannt |
| `GET /router/routes` liefert eigene und aktive globale Routen samt Deployments | die Bibliothek kann nachsehen, welche Modelle ein Name erreicht |
| Vorrang: eigene aktive Route, dann globale aktive, dann `provider/modell` | dieselbe Reihenfolge beim Nachsehen |
| Antwort nennt in `model` das Upstream-Modell | einzige Angabe, wer geantwortet hat → `last_model` |
| Cache auf Provider- **und** Router-Routen, Treffer nicht gekennzeichnet; `ignore-caching=true` liest und schreibt nicht | Bibliothek muss den Cache dokumentieren und umgehen können |
| POST/PUT/DELETE `/router/routes`; DELETE antwortet 200 **ohne Körper**; 409 bei doppeltem Namen, 404 bei unbekannter id | Verwaltung über eigene Methoden; leerer Körper darf nicht als Fehler gelesen werden |

## Umfang

Drin:
- `provider="router"` als dokumentierter dritter Provider
- Körper für Namen am Router: `build_body(…, upstream=…)` und
  `reasoning_for_responses(…, upstream=…)` bauen **einen** Körper für alle
  erreichbaren Modelle; Pflichtform (Token-Feld, `temperature`) muss
  übereinstimmen, sonst `ValidationError` vor dem Senden; Optionales
  (Denk-Schalter, Vorgabe für `reasoning_effort`/`verbosity`) nur, wenn alle es
  nehmen; ein ausdrücklicher Wert muss zu allen passen
- `Route`, `Deployment`; `routes()`, `create_route()`, `replace_route()`,
  `delete_route()`; die Routenliste wird wie die Modellliste kurz gecacht,
  jede eigene Änderung leert diesen Cache
- `last_model` nach einer Router-Antwort = das Modell, das die Antwort nennt
- `BildungsAPI(gateway_cache=False)`: jede generierende Anfrage trägt
  `ignore-caching=true`
- REFERENCE, README, Skill, TRAPS (je beide Sprachen), CHANGELOG, Beispiel
  `27_bapi_router.py`, Offline- und Live-Tests
- Berichtigung: der Docstring eines Tests behauptet, Bearer ergebe 401 —
  gemessen 200

Nicht drin:
- **Administrations-Endpunkte** (`/administration/llm-routing/*`): globale
  Routen, Status, Reload — brauchen ein Admin-Konto
- **Änderungen an `virtual_models`**: bleibt. Es rankt nach Last, die der
  Router laut Doku nicht nutzt, und es geht an jedem Gateway
- **Routen, die GPT-5/o mit anderen Modellen mischen**: `ValidationError`, bis
  gemessen ist, ob die AcademicCloud `max_completion_tokens` annimmt — eine
  Messung mit anderen Modellen als luna, außerhalb der Vorgabe
- ein Cache-Schalter je Aufruf und `clear-cache` je Anfrage (YAGNI; die Route
  leert ihren Cache über `replace_route(…, clear_cache=True)`)

## Ansatz

| | Wie | Dafür | Dagegen |
|---|---|---|---|
| **A · Router als Provider** (gewählt) | `provider="router"`; Körper nach den Modellen hinter dem Namen; Verwaltung in `bapi/router.py`, dünne Methoden an `BildungsAPI` | so beschreibt das Gateway sich selbst (`/provider` listet `router`); jede vorhandene Methode geht sofort mit | `chat`/`respond` brauchen für den Körper einen Blick in die Routenliste |
| B · eigene Klasse `BapiRouter` | wie `BapiTemplates` | getrennt | dieselbe OpenAI-Oberfläche ein zweites Mal — eine Kopie von `chat`, `respond`, `passthrough` |
| C · nur dokumentieren | `call()` mit eigenem Körper | kein Code | `chat` mit einer GPT-5-Route scheitert mit 400; Cache bleibt unsichtbar |

## Architektur

- `src/edusharing/bapi/router.py` (neu): `ROUTER`, `Deployment`, `Route`,
  `upstream_of(name, routes)`, `answered_by(which, response, sent)`,
  `upstream_lookup(api, which)`, `list_routes`, `create_route`,
  `replace_route`, `delete_route`
- `body.py`: Parameter `upstream` an `build_body` und
  `reasoning_for_responses`; ohne ihn bleibt alles, wie es ist
- `choice.py`: `last_model` über `router.answered_by`
- `client.py`: `gateway_cache`, `_request(cacheable=…)`, Routenliste im Cache,
  vier dünne Methoden, `chat` holt die Routen vor der Modellwahl
- `passthrough.respond`: dasselbe wie `chat`
- `_response.py`: `_whole` für Ganzzahlen aus fremden Antworten

Abhängigkeiten: `router` kennt `client` nur unter `TYPE_CHECKING` — wie
`passthrough`.

## Aufgaben (je erst der rote Test)

1. `body.py`: `upstream` — gleiche Form, gemischte Form, Denk-Schalter,
   Vorgabe und ausdrücklicher Wert je Familie
2. `router.py`: Werte lesen und schreiben, `upstream_of` in der Reihenfolge des
   Gateways
3. Verwaltung: Pfade, Körper, Wiederholungsregeln (Anlegen und Löschen nicht
   wiederholen, Ersetzen schon), leerer Körper beim Löschen, Cache und sein
   Leeren
4. `chat`/`respond` über den Router: Körper nach Route, nach Muster, ohne
   lesbare Routenliste; `last_model`
5. `gateway_cache=False`
6. Doku und Beispiel; Wachen `test_docs_*` grün
7. Live-Test mit Wegwerf-Route, nur luna, Aufräumen im `finally`

## Prüfung

- `uv run ruff check .`, `uv run mypy`, `uv run pytest -q` vor jedem Commit
- `uv run python scripts/sync_skill.py --check`
- `-m live` nur für die neuen Router-Tests (luna); keine Route darf übrig bleiben
- CI nach dem Push
