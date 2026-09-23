# edu-sharing Python-Client — Architektur und Entwurf

Stand: 15.09.2026 · Status: **Metadatenprofile, Cache und zusammengesetzte Flows
für 0.3.0 sind umgesetzt und in main gemergt**. Der
[Umsetzungsbericht](audits/2026-09-14-functional-implementation.md) dokumentiert
die abgeschlossenen Arbeiten, Prüfungen und verbleibende Live-Abnahme.
Historische Etappen und Messungen unten behalten ihre ursprünglichen Daten;
Arbeitslisten stehen in [`docs/plans/`](plans/).

`uv run pytest --collect-only -q` zählt die Offline-Suite; `-m live` und
`-m write` wählen Tests aus, die ein echtes Repositorium brauchen. Beispiele aus
[`docs/examples/`](examples/) werden als Tests ausgeführt. Jeder öffentliche
Name **und jedes Feld jedes Objekts** steht in
[`REFERENCE.de.md`](REFERENCE.de.md) / [`REFERENCE.md`](REFERENCE.md), und der
Skill nennt sie ebenfalls. `tests/test_docs_complete.py` prüft die
Vollständigkeit; `tests/test_docs_inventories.py` prüft die Verzeichnisse in
diesem Dokument und in den READMEs.

Eine Python-Bibliothek, die die REST-API eines edu-sharing-Repositoriums und
der Dienste daneben (b-api) mit wenig Code zugänglich macht. Die
Metadaten-Konventionen der Instanz werden über ein explizites `MetadataProfile`
konfiguriert.

> Dies ist die deutsche Fassung von [`ARCHITECTURE.md`](ARCHITECTURE.md). Beide
> werden zusammen gepflegt, die Messwerte sind dieselben.

---

## 1. Warum überhaupt

| Was es heute gibt | Warum es nicht reicht |
|---|---|
| `oeh-search-etl/edu_sharing_openapi/` — generierter Client (openapi-generator 7.8.0) | einverleibt, nicht auf PyPI, synchron, 300+ Modelle, und kennt **keine** der gemessenen Fallen. Wer damit schreibt, bekommt `200 OK` und nichts gespeichert. |
| `wlo-mcp-sc` — MCP-Server (TypeScript, ~30.000 Zeilen) | Die faktische Referenzimplementierung der Fachlogik — aber TypeScript, und die Vokabulare sind für WLO **fest verdrahtet** (`vocabs.ts`). |
| Blankes `requests`/`httpx` | Jede Anwendung baut die 17 Eigenheiten neu — oder läuft hinein. |

**Auf PyPI gibt es keinen edu-sharing-Client.** Der Namensraum war frei.

Der Wert dieser Bibliothek ist nicht der HTTP-Zugang — der ist trivial. Es ist
das **gemessene Verhalten**: welcher Schreibweg für welche Eigenschaft gilt,
dass eine `200` kein Beleg für Speicherung ist, dass es zwei Sammlungssuchen
gibt und keine die andere enthält.

## 2. Der zentrale Widerspruch — und wie er aufgelöst wird

Zwei Anforderungen ziehen gegeneinander:

* **generisch** — andere edu-sharing-Instanzen haben andere Metadatensätze,
  andere Eigenschaften, andere Vokabulare. Nichts darf fest verdrahtet sein.
* **wenig Code** — `repo.search("Photosynthese", subject="Biologie")` statt
  erst den Metadatensatz zu laden, URIs aufzulösen und Kriterien zu bauen.

**Auflösung:** Die Vokabularauflösung geschieht **zur Laufzeit gegen den
Metadatensatz der vorliegenden Instanz**, nicht gegen eine eingebaute Tabelle.

```python
repo.vocab.resolve("ccm:taxonid", "Biologie")
# → POST /mds/v1/metadatasets/-home-/{mds}/values   {"pattern": ""}
# → "http://w3id.org/openeduhub/vocabs/discipline/080"
```

`subject="Biologie"` benötigt einen Alias auf die Fach-Eigenschaft der Instanz
und eine MDS-Abfrage, die dieses Kriterium akzeptiert. Ein geladenes Vokabular
oder MDS-Widget beweist weder die Suchbarkeit noch die semantische Rolle eines
Feldes.

Das WLO-Beispiel oben nutzt die Kompatibilitätsvorgaben. Bei einem anderen
Metadatensatz wird ein `MetadataProfile` mit dessen Lese-/Schreibfeldern,
Aliasen und Abfragekonventionen übergeben. Ein explizites `MetadataProfile()`
übernimmt keine WLO-Anwendungsfelder; `metadata_profile=None` wählt für
bestehende Anwendungen `WLO_METADATA_PROFILE`.
Siehe [Konfiguration und Migration](REFERENCE.de.md#metadatenprofile-und-cache-030).

> Gemessen (Staging, 12.08.2026): `pattern: ""` listet alle Werte — das
> dokumentierte `"-all-"` liefert **leer**. `pattern: "Ph"` ist eine
> funktionierende Teilstringsuche, der Endpunkt taugt also zugleich als
> Eingabevervollständigung. Der Kopf `locale: en_EN` liefert englische Labels.

## 3. Schichten

```
┌─ 4  Integrationen ──── MCP-Server · Werkzeugschemata · Framework-Adapter
│                        NICHT Teil von v1 — aber v1 muss sie tragen
├─ 3  Agentenbausteine ─ Formatierung · Budget · Vorlegen · Aufbereiten · Sicherheit
├─ 2b Abläufe ────────── ein Anwendungsfall, ein Aufruf, ein dict — siehe FLOWS.de.md
├─ 2  Ressourcen ─────── repo.search() · node.update() · collection.add() · repo.skills
├─ 1  Profil und MDS ─── Vokabularauflösung · Eigenschaften und ihre Wege
├─ 0  Transport ──────── httpx · Auth · Wiederholung · Nebenläufigkeit · Rückleseprobe · Fehler
├─ geteilt ───────────── fields · ranking · language · strings · dto · urls · retry
│                        am 08.09.2026 aus flows/ herausgeholt (ARC-1), damit
│                        Schicht 2 nicht mehr in Schicht 2b hinaufgreift
└─ _generated ────────── 389 Operationen · 378 Modelle, aus openapi.json

   daneben, nicht darin:
   edusharing.bapi ─────────── das LLM-Gateway
   edusharing.extraction ───── der Textextraktionsdienst
   edusharing.metadata_agent ─ die Schemata hinter ccm:oeh_extendedData
```

Schicht 1 beantwortet auch die Frage, die Dritte nicht beantworten können:
**welcher Schreibweg gilt.** Eigenschaft im Metadatensatz → `PUT /metadata`.
Nicht darin → `POST /property`. Die Bibliothek entscheidet das selbst.

## 4. Getroffene Entscheidungen

| # | Entscheidung | Begründung |
|---|---|---|
| E1 | **Vollständige Endpunktabdeckung** über eine generierte Schicht | 318 Pfade / 389 Operationen / 378 Schemata; alle mit `operationId` → deterministisch generierbar. Kein blinder Fleck. |
| E2 | Generator: **`openapi-python-client`** (Python), nicht der Java-`openapi-generator` | Erzeugt **httpx**-basierte Clients mit async. Der Java-Generator liefert sync/urllib3 — unvereinbar mit E3. Java ist auf dem Zielrechner ohnehin nicht installiert. **Live geprüft, siehe §4.1.** |
| E3 | **Async zuerst, synchroner Mantel** | `AsyncRepository` ist die Wahrheit, `Repository` ein dünner Mantel (Vorbilder: httpx, openai). KI-Anwendungen und Stapelredaktion brauchen Nebenläufigkeit; Notebooks bekommen trotzdem den einfachen Weg. |
| E4 | **Explizite Metadatenprofile je Repositorium** | `MetadataProfile` konfiguriert Anwendungsfelder und Abfragekonventionen. Ein explizites neutrales/eigenes Profil übernimmt keine WLO-Felder; `None` behält das benannte WLO-Kompatibilitätsprofil bei. Version 0.3.0 ist mit HTTP-Mocks geprüft; die Live-Abnahme weiterer Installationen steht noch aus. |
| E5 | **Kein MCP-Server in v1** — aber jeder Baustein für einen | Siehe §6. Der MCP wird später *mit* der Bibliothek gebaut, nicht *in* sie hinein. |
| E6 | Import `edusharing`, Distribution `edu-sharing-python-client` | Der blanke Name `edu-sharing` hätte nach einem offiziellen Client der metaVentis GmbH ausgesehen, von der edu-sharing stammt. |
| E7 | **Englische API-Namen, Repository-Labels in der gewünschten Sprache** | Die Standard-Aliase sind englisch; eigene Profile können andere festlegen. Labels kommen in der angefragten `locale` vom Repositorium, gespeicherte Werte behalten ihre Identität. Deutsche WLO-Labels sind Beispiele. |
| E8 | **Bezeichner werden an genau einer Stelle prozentkodiert** (`urls.path_segment`) | Eine ID per f-String in einen Pfad zu setzen lässt sie aus dem Pfad ausbrechen: gemessen am 27.08.2026 erreichte eine Knoten-ID `../../../admin/v1/applications` einen anderen Endpunkt, und `abc?admin=1` schluckte das angehängte `/metadata`. An jeder der 16 Aufrufstellen zu kodieren hieße 16 Gelegenheiten, es zu vergessen; ein Helfer plus ein Integrationstest, der jede Aufrufstelle abläuft, lässt eine vergessene Stelle laut scheitern. Wichtig, weil unter einem MCP die ID vom Modell kommt, also aus fremden Daten. Siehe Audit F1. |
| E9 | **Zwei Ebenen: API-nahe Objekte und JSON-Abläufe** | Die API-Ebene liefert `SearchResult` und `Node` — richtig, um Python zu schreiben, falsch für alles, was das Ergebnis weiterreicht. `repo.flows.*` verkettet dieselben Aufrufe und endet bei `dict`. Abläufe fügen nichts hinzu; sie sparen Schritte. Getrennt gehalten statt verschmolzen, weil ein Objekt mit Methoden und eine JSON-fähige Struktur wirklich verschiedene Dinge sind und eines von beiden zu wählen das andere unhandlich gemacht hätte. Die Schlüssel der Ausgabe sind die konfigurierten Aliase, die Form hängt also an keinem Profil (siehe E4). |
| E10 | **Neuordnung ist zuschaltbar, und ihre Wortlisten sind ein Parameter** | edu-sharing verknüpft alle Suchwörter mit UND, eine natürlich formulierte Frage findet also nichts — gemessen am 27.08.2026: „Bruchrechnung" 1591 Datensätze, „Ich suche ein Arbeitsblatt zur Bruchrechnung" **0**. So formuliert ein Sprachmodell, die Abhilfe zählt also für das Hauptpublikum dieser Bibliothek. Aus `wlo-mcp-sc` (Apache-2.0) übernommen, mit zwei Änderungen: aus den deutschen Wortlisten wurde ein `LanguageProfile`-Parameter, und die Qualitätssignale lesen die konfigurierten Aliase statt fester WLO-Eigenschaften — eine fest verdrahtete deutsche Liste widerspräche E4. Zuschaltbar, weil sie je Variante eine Anfrage kostet. Die reziproke Rangfusion des Originals wurde **entfernt**: sie gewichtete die Position eines Datensatzes in der Antwort des Repositoriums, und diese Reihenfolge ist messbar unstet (25 Treffer, davon 15 verschieden zwischen gleichen Anfragen), womit die Rangfolge von der Ankunftsreihenfolge abhing — von 30 Mischungen derselben Kandidatenmenge ergaben nur 14 dasselbe Ergebnis. Was bleibt, ist reihenfolgeunabhängig: Qualität (0,8) plus die Frage, welche Varianten einen Datensatz überhaupt zurückgaben (0,2). Gleiche Kandidaten hinein, gleiche Rangfolge heraus; zwei Läufe unterscheiden sich weiterhin, wenn der Index sich unterscheidet. |
| E11 | **Der Template-Modus der b-api ist eine eigene Klasse mit eigenem Anfrageweg** | Das Gateway läuft auf zwei Arten: als Proxy (`BildungsAPI`, der Aufrufer schickt den Prompt) und mit Prompts, die auf dem Server liegen (`BapiTemplates`, der Aufrufer schickt Konfigurations-IDs). Die beiden brauchen **verschiedene Wiederholungsregeln**, gemessen am 11.09.2026: im Template-Modus antwortet eine unbekannte Konfigurations-ID mit 500, und `suggestions` und `qas` speichern ihr Ergebnis — eine 502 oder 504 kann dort also nach getaner Arbeit kommen. Das `_request` des Proxys mitzubenutzen hätte beides wiederholt. Methoden an `BildungsAPI` hätten dem Proxy eine zweite Verantwortung gegeben und einen Grund, sich mit jeder Template-Route zu ändern. Also: eine eigene Klasse, gebaut aus dem, was sich teilen lässt — `RetryPolicy`, die Fehlerklassen, die Weiterleitungs- und Nicht-JSON-Fehler, die Adressprüfung und die Antwort-Parser des Proxys. Keine der beiden Klassen braucht die andere; einen gemeinsamen Verbindungspool bekommt, wer beiden denselben `client=` gibt — die Konvention der Bibliothek. `tests/test_bapi_client.py` pinnt die öffentlichen Namen des Proxys, damit er nicht versehentlich wächst. |

### 4.1 Machbarkeitsnachweis (durchgeführt am 27.08.2026 gegen Staging)

E1 und E2 sind **nicht angenommen, sondern gemessen** — mit einem Befund, der
die Erzeugungskette sonst zerlegt hätte:

1. **Der Generator erzeugt aus der unveränderten Spezifikation ungültiges Python.**
   244 Pfadparameter tragen ein `schema.default` (`-home-`, `-default-`,
   `-userhome-`); folgt darauf ein Parameter ohne Vorgabewert, bekommt man

   ```python
   def _get_kwargs(
       repository: str = '-home-',      # Vorgabe aus der Spezifikation
       metadataset: str = '-default-',  # Vorgabe aus der Spezifikation
       query: str,                      # ← SyntaxError
   ```

   **145 von 1131 Dateien waren kaputt** (12,8 %) — alle unter `api/`, die 701
   Modelle blieben sauber. Der Generator meldet das nur als Warnung und endet
   mit **Code 0**. Wer nicht nachsieht, hält es für einen geglückten Lauf.

2. **Eine deterministische Vorverarbeitung der Spezifikation behebt es
   vollständig.** Nach dem Entfernen der 244 Vorgabewerte: **1131 Dateien, 0
   Syntaxfehler.** Der Vorgabewert geht nicht verloren — er ist eine
   Bequemlichkeit der Weboberfläche, und die Bequemlichkeitsschicht setzt
   `-home-` ohnehin selbst.

3. **Alle 389 Operationen haben eine `asyncio`-Variante.** Passend zu E3.

4. **Live-Aufruf gelungen:** `GET /_about` durch den generierten Async-Client →
   `200`, **edu-sharing 11.0**, 32 Dienste.

Prüfung und Reparatur stehen beide in `scripts/generate_client.py`. Das Skript
endet mit Code 1, wenn auch nur eine Datei nicht parst; die Syntaxprüfung
gehört zum Erzeugen, sie ist nicht optional. Die CI erzeugt bei jedem Push neu
und verlangt einen sauberen Diff — ohne das ist „regenerierbar" eine Behauptung
und keine Tatsache.

Seit dem 14.09.2026 weist ein deterministischer Nachlauf auch leere und ganze
Punkt-Pfadparameter (`.`, `..`) vor dem Adressaufbau zurück (Audit R10).
Die generierte Schicht wirft `ValueError`, ohne die handgeschriebene Schicht
zu importieren. Der Nachlauf prüft die Kodierungsausdrücke des festgehaltenen
Generators anhand des Syntaxbaums und bricht bei unerwarteter Form ab;
wiederholtes Anwenden ist idempotent. Regressionstests prüfen die Ablehnung,
gültige Kodierung und das erneute Generieren.

> **Der unterstützte Ausgabeort ist der im Projekt.** `--output` in ein
> Verzeichnis ausserhalb des Projektlayouts ergab **556 abweichende Dateien**
> (gemessen 09.09.2026) — andere Formatierung und `typing_extensions.Self`
> statt `typing.Self`. Der Generator liest die umgebende `pyproject.toml`:
> `requires-python >=3.11` lässt ihn `typing.Self` schreiben (weshalb
> `typing-extensions` keine Abhängigkeit ist, Audit DEP-1), und
> `line-length = 100` bestimmt die Formatierung. Dieselbe Spec, derselbe
> Generator, derselbe Inhalt — eine andere Form. Die Herkunftsnotiz hält Spec
> und Generatorfassung fest, nicht das umgebende Projekt, und bildet diesen
> Unterschied deshalb nicht ab. Also am vorgesehenen Ort erzeugen.

> **Inhaltstypen, die die Spec erfindet.** Am 09.09.2026 gegen die
> Referenzspezifikation ausgezählt: **sieben** Antworten deklarieren einen Typ,
> mit dem der Generator nichts anfangen kann — sechsmal `application/text`
> (kein gültiger MIME-Typ) an `GET .../permissions/jwt` und einmal `*/*` (ein
> Platzhalter, kein Typ) an `GET /ltiplatform/v13/content`. Zwei der sieben
> sind **Erfolgsantworten**, und bis dahin stand hier „die einzige verbleibende
> Warnung: eine `500`" — ein Satz, der eine Prüfung beruhigt, statt sie zu
> leiten. Beide Endpunkte hatten deshalb gar keinen `200`-Zweig: `parsed=None`,
> und mit `raise_on_unexpected_status` ein `UnexpectedStatus` für Status 200
> (Fremdprüfung F15).
>
> `normalise_content_types` in `scripts/generate_client.py` ersetzt sie vor dem
> Erzeugen und entscheidet dabei am **Schema** daneben, nicht am erfundenen
> Typ: `{"type": "string"}` wird `text/plain`, ein `$ref` wird
> `application/json`. Alle auf Text abzubilden war der erste Anlauf und
> tauschte einen Fehler gegen einen anderen — die Fehlerzweige des
> JWT-Endpunkts lasen dann `ErrorResponse.from_dict(response.text)` und
> brachen mit `ValueError` ab, wo sie vorher `None` gaben. Normalisiert wird
> die Spec, nie die erzeugte Datei. `tests/test_generated_layer.py` zählt
> nach, was übrig ist, damit die Zahl in diesem Absatz nicht unbemerkt
> altert.

### Was E1 kostet und wie es eingehegt wird

Vollständige Abdeckung heißt Bindung an eine edu-sharing-Version. Gegenmittel:

1. Erzeugt wird gegen eine **Referenzspezifikation**, die im Repository liegt
   und versioniert ist.
2. `scripts/generate_client.py` erzeugt gegen **jede** Instanz neu
   (`GET <repo>/rest/openapi.json`) — wer eine andere Version fährt, baut sich
   seine eigene Schicht.
3. Die handgeschriebenen Schichten 0–3 hängen **nur** an den rund 30 tatsächlich
   benutzten Operationen. Bricht die generierte Schicht, bricht die Bibliothek
   nicht.
4. `repo.raw.get/post(...)` bleibt als Notausgang offen.

## 5. Wie es sich anfühlen soll

```python
from edusharing import Repository

repo = Repository.from_env()          # EDU_SHARING_URL / _USER / _PASSWORD
repo = Repository("https://repository.staging.openeduhub.net")   # anonym, nur lesend

# --- Lesen: Labels, keine URIs. Aufgelöst gegen den MDS DIESER Instanz.
for hit in repo.search("Photosynthese", subject="Biologie", level="Sekundarstufe I"):
    print(hit.title, hit.url)

# --- Schreiben: zusammengeführt, zurückgelesen, wirft bei stillem Verlust
node = repo.node("abc-123")
node = node.update(title="Neuer Titel", description="…")
node = node.add_keywords("Weimar (Ort)")     # ergänzen, nicht überschreiben

# --- Sammlungen: beide Suchwege, weil keiner den anderen enthält
repo.find_collections("Optik")
repo.add_to_collection(collection_id, node.id)

# --- Notausgang: jede der 389 Operationen
repo.raw.json("GET", "/config/v1/values")
```

Der Fehlerfall, der die Bibliothek rechtfertigt:

```
SilentDropError: Not stored: ccm:oeh_collection_compendium_text
  (HTTP 200, absent or different after reading back). …
  node.set_property(...) bypasses the metadata set's filtering.
```

## 6. Was ein komplexer MCP brauchen wird — und warum es in v1 steckt

Der MCP-Server ist nicht Teil von v1. Die Bausteine, ohne die er sich später
nicht bauen ließe, schon. Abgeleitet aus `wlo-mcp-sc`:

| Baustein | Warum ein MCP ihn braucht | Stand |
|---|---|---|
| **Zugangsdaten je Anfrage** | Ein Server bedient viele Nutzer — globaler Auth-Zustand ist ein Leck. | ✅ `auth`, `transport` |
| **Vorlegen statt ausführen** | Der Agent muss zeigen können, *was* er ändern würde, bevor er es tut. | ✅ `agent/confirm` |
| **LLM-Formatierung und Budget** | Knoten → kompakter Text, gedeckelt, mit erhaltener URL und Knoten-ID (die ein Modell sonst wegparaphrasiert). | ✅ `agent/format` |
| **Prompt-Injection entschärfen** | Fremder Repositoriumsinhalt landet im Modellkontext. | ✅ `agent/sanitize` |
| **SSRF-/Private-Host-Schutz** | URLs aus fremdem Inhalt werden abgerufen. | ✅ `agent/safety` |
| **Strukturierte Ergebnisse statt Ausnahmen** | Ein Werkzeug gibt Fehler als *Text* zurück; eine Ausnahme beendet den Zug. | ✅ `agent/result` |
| **Nebenläufigkeit und Drosselung** | Auffächern über viele Knoten, ohne das Repositorium zu überfahren. | ✅ `transport`, `bapi/client`, `bapi/templates` |
| **Rückmeldung zur Auflösung** | „subject 'Bio' nicht auflösbar — meintest du Biologie?" statt stiller Leere. | ✅ `search`, `results` |
| **Doppelte zusammenführen** | Die beiden Sammlungswege auf der Knoten-ID vereinen. | ✅ `collections` |
| **Cache mit Verfallszeit** | Vokabulare und Modelllisten sind teuer und ändern sich selten. | ✅ `vocab` (`DEFAULT_CACHE_SECONDS`, 1 h — erst seit 08.09.2026 wirklich, Audit PRF-4), `bapi/client` (`models_cache_seconds`, 30 s) |

Das ist Schicht 3 (`edusharing.agent`). Sie ist **frameworkneutral** — kein MCP,
kein LangChain-Import. Der MCP-Server ist danach ein dünnes Adapterprojekt.

In Etappe 4 bewusst **nicht** gebaut: ein Reranker. Ohne konkreten
Anwendungsfall wäre er geraten gewesen, und die beiden Sammlungswege sind auf
der Knoten-ID bereits vereint. Der Anwendungsfall kam dann doch — eine
natürlich formulierte Frage findet nichts, weil edu-sharing alle Wörter mit UND
verknüpft. Etappe 5 hat ihn nachgeliefert, zuschaltbar und mit Wortlisten als
Parameter (E10).

## 7. Gemessene Grundlagen, auf denen der Entwurf steht

Nicht angenommen, sondern nachgeprüft (Staging, 27.08.2026, wo nicht anders
vermerkt):

**edu-sharing**

* Die Referenzinstanz meldet **edu-sharing 11.0** (`GET /_about`), 32 Dienste.
* `GET /rest/openapi.json` → 1,34 MB, OpenAPI 3.0.1, 318 Pfade / 389
  Operationen / 378 Schemata, 36 Familien, **alle mit `operationId`**.
  `swagger.json` gibt es nicht. Größte Familien: ADMIN v1 (61), NODE v1 (53),
  IAM v1 (47), Assignment v1 (18), COLLECTION v1 (16), SEARCH v1 (13),
  MDS v1 (5).
* `securitySchemes` = `basicAuth` + `cookieAuth`. **Kein Bearer.** Ein
  Bearer-Kopf wird *ignoriert, nicht abgelehnt* — die Anfrage sieht
  authentifiziert aus und ist es nicht. Der gefährlichste Fehler, den ein
  Client machen kann.
* Falsche Zugangsdaten geben **überall 401** — kein Rückfall auf „nur
  Öffentliches". Ein Tippfehler im Passwort legt jeden Aufruf lahm, statt den
  Zugang abzustufen.
* Der Metadatensatz ist **17,2 MB** — nie im Anfrageweg. Vokabular kommt aus
  `POST /mds/v1/metadatasets/-home-/{mds}/values`.
* `GET /search/v1/metadata?nodeIds=a&nodeIds=b` **ist kein Stapelabruf** — zwei
  IDs ergeben genau ein Ergebnis. Wer ihn dafür hält, verliert Knoten still.

**b-api** *(Spring Boot, nicht FastAPI — die 404-Spur verrät es)*

* Genau zwei Anbieter: `academiccloud`, `openai`. Andere → `400 Provider … not
  found`.
* `/embeddings`, `/completions` → **403** von Spring Security. Nicht
  freigeschaltet.
* Ohne Schlüssel → 401. Die Auth ist `X-API-KEY`, **nicht** Bearer.
* `openapi.json`, `/docs`, `/health` liefern HTML (SPA-Rückfall) — jede
  Endpunktsuche ist Raten. Als bekannte Grenze festgehalten.
* → „die b-api fahren" heißt **Politik**, nicht Breite: Modellwahl über
  `demand`/`status`, familienweise Eigenheiten der Anfrage
  (`max_completion_tokens` für GPT-5/o, `enable_thinking:false` für Qwen3 —
  aber **nicht** für Mistral, das mit 400 antwortet), Wiederholung bei
  429/502/503/504, Semaphor, `content or reasoning` beim Lesen.

**Der Suchindex führt Knoten, die es nicht mehr gibt.** Gemessen am 27.08.2026
gegen Staging: von 25 Treffern zu „Physik" waren **4 nicht abrufbar** —
`NotFoundError` von `/node/v1/nodes/-home-/{id}/metadata`, obwohl der Treffer
Titel und vollständige Metadaten in der Suchantwort trug. Wer Suche und
Detailabruf verkettet — und genau das tut ein MCP —, muss das überstehen.
Festgehalten, weil es wie ein Fehler der Bibliothek aussieht und keiner ist.

**Drei verschiedene Begriffe verbinden Knoten, und sie sind leicht zu
verwechseln.** Eine **Sammlung** ist ein Behälter von Referenzen. Eine
**Beziehung** (`/relation/v1`) verbindet zwei Knoten, die für sich stehen —
eine Reihe und das, worauf sie aufbaut — und führt die Gegenrichtung
automatisch mit. Ein **Serienobjekt** gehört zu seinem Elternknoten und hat
ohne ihn kein Leben: ein Lösungsblatt, ein Handout. Nur das letzte musste
rückentwickelt werden: gemessen am 27.08.2026 antwortet
`type=ccm:io_childobject` mit HTTP 500, weil `ccm:io_childobject` ein *Aspekt*
ist, und der funktionierende Aufruf lautet `type=ccm:io` mit
`assocType=ccm:childio` und `aspects=ccm:io_childobject`. Aus der
Ideendatenbank übernommen, die es produktiv einsetzt.

**Schreiben kann halb gelingen, und die Antwort sagt es nicht.** Drei Fälle,
gemessen am 28.08.2026, alle mit HTTP 200:

* `ccm:oeh_lrt_aggregated` wird aus `ccm:oeh_lrt` abgeleitet. Beim Anlegen
  mitgeschickt kommt es nicht zurück, während `ccm:taxonid` im selben Aufruf
  ankommt.
* Ein `cm:folder` mit `cm:title` anzulegen überschreibt diesen Titel mit
  `cm:name`. Derselbe Titel an einem `ccm:io` kommt an — es ist eine Regel des
  Ordnertyps. Nachträglich mit `update()` gesetzt funktioniert er.
* Schlagworte, die beim Anlegen einer *Sammlung* mitgeschickt werden, fallen
  weg; sie brauchen einen zweiten Aufruf.

Die ersten beiden sind der Grund, warum `Nodes.create` inzwischen zurückliest,
wie `update` und `set_property` es immer taten. Es kostet nichts: die
POST-Antwort trägt den angelegten Knoten und zeigt den Verlust bereits. Den
Ordnertitel-Fall hat die Prüfung von selbst gefunden — jeder Wegwerf-Ordner in
den Tests dieses Repositoriums hatte einen Titel mitgegeben, der nie ankam.

**Ein Knoten, den eine Anwendung anlegt, ist für seinen Urheber sichtbar und
für sonst niemanden** — und keines der beiden Dinge, die das zu ändern
scheinen, tut es. Gemessen am 28.08.2026 in einem Wegwerf-Ordner:

* Den Knoten in eine Sammlung zu referenzieren veröffentlicht das Original
  nicht. Die Ideendatenbank hat das produktiv gefunden; hier reproduziert es
  sich.
* `scope="PUBLIC"` an der Sammlung tut es auch nicht — die Sammlung kommt mit
  `isPublic=False` zurück und ohne Eintrag für alle. Der Scope entscheidet, wo
  eine Sammlung gelistet wird, nicht, wer sie öffnen darf.

Veröffentlichen heißt: ein Eintrag in der Rechteliste, `GROUP_EVERYONE` mit
`Consumer`. Vier Dinge daran prägen `permissions.py`:

* `POST` **ersetzt** die lokale Liste, statt in sie hineinzuschreiben. Ohne
  Zusammenführen nähme Veröffentlichen allen anderen still ihre Rechte.
* Ein `GROUP_`-Name ohne Gruppe dahinter wird mit einer `200` verworfen — der
  gleiche stille Verlust wie bei Eigenschaften, weshalb auch dieser Schreibweg
  zurückliest. Ein **Benutzer**name wird überhaupt nicht geprüft und in jedem
  Fall gespeichert, die Prüfung kann einen vertippten also nicht fangen. Diese
  Grenze wird benannt statt übertüncht.
* Ein Knoten erbt den öffentlichen Zugang seines Elternknotens ohne eigenen
  Eintrag. Wer nur die lokale Liste liest, nennt einen weltlesbaren Knoten
  privat.
* Der Antwortkörper ist leer, die Rückleseprobe ist also der einzige Beleg,
  den es gibt.

Die eine gute Nachricht ist umsonst zu haben: jede Knotenantwort trägt
`isPublic`, und gemessen stimmt es mit der Rechteliste in beide Richtungen
überein, Vererbung eingeschlossen. `Node.is_public` und das Feld `public` in
den Abläufen kosten deshalb keine Anfrage.

**Ein Weg nach oben endet, wo die Rechte des Kontos enden, und sagt das auch.**
`GET .../parents` mit `fullPath=true` antwortet einem gewöhnlichen Konto mit
**403** — der vollständige Pfad führt durch Bereiche, die es nicht lesen darf.
Ohne den Parameter reicht die Antwort so weit, wie es erlaubt ist, und benennt
die Grenze in `scope`. `placement` gibt die Grenze weiter, statt einen
abgeschnittenen Pfad als vollständigen durchgehen zu lassen.

Zwei weitere Messungen prägen dieses Modul. Ohne `propertyFilter=-all-` kommen
die Vorfahren mit leeren Eigenschaften an — Namen, aber keine Titel, was eine
Brotkrumenspur nutzlos macht. Und der erste Eintrag der Antwort ist der Knoten
**selbst**, wer ihn nicht wegnimmt, führt einen Knoten als seinen eigenen
Vorfahren.

**Zwei weitere Fehler kommen verkleidet**, beide gemessen am 28.08.2026 beim
Weg nach oben von gewöhnlichen Suchtreffern aus:

* `/usage/v1/usages/node/{id}/collections` antwortet mit **500** für eine ID,
  für die der Knotenendpunkt 404 sagt.
* `/node/v1/nodes/.../parents` antwortet mit **500 AccessDeniedException** für
  fremdes Material, während derselbe Endpunkt bei einem eigenen Knoten ein
  sauberes 403 liefert.

Beide kommen zum Gastnutzer-Fall in `error_from_response`, und aus demselben
Grund: als `ServerError` wiederholt der Transport dreimal eine Anfrage, die nie
gelingen kann, und wer `NotFoundError` oder `PermissionDeniedError` fängt,
sieht sie nie. Dass der Suchindex Knoten führt, die das Repositorium nicht mehr
hat — 4 von 25 Treffern, gemessen —, macht den ersten davon zum Alltagsfall
statt zur Kuriosität.

**Zwei Endpunkte antworten mit leerem Körper und legen die Wahrheit anderswo
ab.** Bewerten und Kommentieren melden beide 200 und geben nichts zurück, beide
lesen deshalb den Knoten erneut — derselbe Grund, aus dem `permissions.py` es
tut. Zwei Messungen vom 28.08.2026 prägen diese Module:

* **Eine Bewertung von `0` ist eine Stimme, kein Zurücksetzen.** Danach zeigt
  der Knoten `count: 1, rating: 0.0`. Die Ideendatenbank dokumentiert die Null
  als Weg, eine Bewertung zu löschen; auf Staging senkt sie stattdessen den
  Durchschnitt, weshalb `rate()` sie ablehnt und auf `unrate()` zeigt. `DELETE`
  ist das Zurücksetzen, und es antwortet auch dann mit 200, wenn es nichts zu
  entfernen gab.
* **Ein Kommentartext wird Byte für Byte gespeichert.** Es findet kein
  JSON-Parsen statt, während der Inhaltstyp trotzdem `application/json` sein
  muss (alles andere ist 415). Den Text durch `json=` zu schicken würde die
  Anführungszeichen mitspeichern. Bearbeiten ist ein `POST` auf den Kommentar;
  ein `PUT` dort legt einen Kommentar zum Kommentar an und antwortet mit 500.

Die gute Nachricht wiederholt sich: die Knotenantwort trägt `rating` —
Durchschnitt, Anzahl und die eigene Stimme dieses Kontos —, eines zu lesen
kostet also keine Anfrage, genau wie bei `isPublic`.

**Ein ganzer Endpunkt kann 200 antworten und nichts tun.** `/suggestions/v1`
ist ein Zwischenlager mit Protokoll, kein Mechanismus: gemessen am 28.08.2026
ließ ein auf `ACCEPTED` gesetzter Vorschlag die Eigenschaft des Knotens leer —
dasselbe Ergebnis, das wlo-mcp-sc am 01.08.2026 gemessen hat. Den Wert
anzuwenden bleibt Sache des Aufrufers, über den gewöhnlichen Schreibweg mit
seiner Rückleseprobe.

Schlimmer noch: die IDs für diesen Aufruf gehören in die **Query**, nicht in
den Körper. Als JSON-Körper geschickt werden sie ignoriert, jeder Vorschlag
bleibt `PENDING`, und eine 200 steht davor. Ein Live-Test hat genau das während
der Umsetzung gefangen, was das Argument dafür ist, überhaupt Live-Tests zu
haben: der Offline-Mock war auf dieselbe falsche Annahme geschrieben wie der
Code und stimmte ihm deshalb zu. `decide()` liest die Zustände deshalb zurück.

Der Workflow-Verlauf ist **neueste zuerst** geordnet — gemessen durch zweimal
Einreichen. `submit()` liest ihn zurück und nimmt den ersten Treffer, eine
wiederholte Einreichung liefert also den eben gemachten Schritt und nicht einen
älteren, der genauso aussah.

**`limit` war ein Deckel je Weg, kein Deckel auf das Ergebnis.** Gemessen am
28.08.2026: `collections.find("Biologie", limit=10)` gab **19** Treffer zurück,
`limit=3` gab 4 — jeder Weg wurde nach `limit` gefragt und die Antworten wurden
aneinandergereiht, während zwei Ablauf-Docstrings `limit` als „wie viele
zurückkommen" beschrieben. Für das Hauptpublikum dieser Bibliothek ist das
nicht kosmetisch: ein Modellkontext mit Budget bekam still das Doppelte des
Bestellten. Die Reparatur musste beide Wege vertreten lassen, die
zusammengeführte Liste wird deshalb im Wechsel genommen, bevor sie geschnitten
wird — aneinanderreihen und dann schneiden ließe Weg A den Deckel bei jeder
breiten Anfrage allein füllen, und Weg B findet nachweislich Sammlungen, die A
nicht findet.

**Eine Teilantwort ist besser als eine Ausnahme, und vier Abläufe wussten
das nicht.** Gemessen am 28.08.2026: `flows.placement()` warf bei **18 von 20**
Materialtreffern einer Suche, weil `/parents` bei fremdem Material mit *500
AccessDeniedException* antwortet, während es bei einem eigenen Knoten ein
sauberes 403 liefert — und die Sammlungshälfte antwortete jedes einzelne Mal.
Über vier Suchbegriffe hinweg hätten von 58 Knoten, bei denen der Ablauf warf,
48 eine brauchbare Antwort geliefert, 4 davon mit echten
Sammlungszugehörigkeiten. Das Prinzip stand schon in `describe_many`, in
`collections.find` („half a result is usable, a faked empty one is not") und in
`flows/tree.py` — umgesetzt war es an drei von sieben Stellen, an denen es
gilt. `placement`, `search_all` und `search_in_collection` melden den
verweigerten Teil jetzt (`failed`, `error`, `unreadable`) und werfen nur, wenn
nichts mehr zu berichten ist. Nach der Änderung antworten 16 derselben 20; die
4, die noch werfen, sind die toten Indexeinträge, bei denen beide Hälften
ausfallen.

**Eine Umleitung galt als Erfolg.** `status_code < 400` ließ jede 3xx als
Antwort durch. Dieser Client folgt Umleitungen nicht — `follow_redirects` bleibt
bei der httpx-Vorgabe `False`, weil eine Umleitung vom Repositorium weg die
Zugangsdaten mitnähme —, zurück kam also der leere Körper der Umleitung. Bei
`Content.download` sind das null Bytes statt der Datei, still: dieselbe Familie
wie das Rücklese-Problem, eine Statusklasse weiter. Gemessen leitet auf der
Referenzinstanz kein Download um (0 von 8), der Fall war also latent, nicht
akut; hinter einem Proxy, der auf eine Anmeldeseite umlenkt, ist er es nicht.

**Sammlungen bilden einen gerichteten Graphen, keinen Baum.** Eine
Untersammlung kann unter mehreren Elternsammlungen hängen, und zwei können
untereinander hängen. Jeder Gang in `flows/tree.py` entdoppelt deshalb über die
ID und deckelt, wie viele Sammlungen er öffnet — und sagt in seiner Antwort,
wenn er früh aufgehört hat. Still abzuschneiden liest sich wie Vollständigkeit,
und ein Aufrufer kann ein leeres Ergebnis nicht von einem unfertigen
unterscheiden.

Eine Folge davon hat sich während der Umsetzung selbst gefangen: `browse_tree`
listet Kinder, die es nicht geöffnet hat, weil sie mit der Antwort ihrer Eltern
umsonst mitkommen. `search_in_collection` las Material aus allen davon, was am
Deckel des Aufrufers vorbeilief. Ein vor dem Code geschriebener Test hat es
gefunden; derselbe Deckel begrenzt jetzt beides.

**Der Page Builder schreibt Dokumente, die niemand prüft.** Die kuratierte
Seite einer Sammlung liegt in zwei JSON-Klumpen — `ccm:page_config` an einem
Ordner, `ccm:page_variant_config` an jedem seiner Kinder — und der
Eigenschaftsweg, der sie speichert, prüft nichts. Gemessen: er nahm die
wörtliche Zeichenkette `"not json at all"` mit einer `200` an, und er nahm die
Eigenschaft an einem Knoten an, der gar kein Seitenordner ist.

`pages.py` ist ganz davon geprägt. Das Lesen wirft nie bei einem kaputten
Dokument; es meldet `readable=False`, weil eine schlechte Variante nicht die
ganze Seite kosten darf. Das Schreiben geht den anderen Weg und verweigert
alles, was es nicht belegen kann — kein Dokument, kein JSON, kein Objekt, keine
Variantenliste, Variante nicht darin — und **bearbeitet** den gespeicherten
Klumpen, statt einen zu komponieren, damit jeder Schlüssel, der dem Page
Builder gehört, eine Änderung dieser Bibliothek überlebt.

Zwei weitere Dinge musste die Form berücksichtigen. Ein Dokument ohne
`default` zeigt `variants[0]`: „nichts gewählt" und „das erste gewählt" sind
für einen Besucher nicht zu unterscheiden und für einen Schreibvorgang
verschieden, deshalb benennt `by_position` den Unterschied. Und `render()`
sitzt am Zugriffsobjekt, nicht am Wertobjekt: eine `async`-Methode an einem
eingefrorenen Wertobjekt wäre die erste dieser Bibliothek gewesen, und
`SyncNodePage.get()` würde dem synchronen Aufrufer dann ein Objekt geben,
dessen `render()` eine nicht abgewartete Coroutine ist — genau die Falle, gegen
die die synchrone Fläche existiert.

## 8. Etappen

| # | Inhalt | Fertig, wenn |
|---|---|---|
| **0** | ~~Generatorkette~~ | ✅ **fertig** — `scripts/generate_client.py`, geprüft (§4.1) |
| **1** | ~~Transport, Auth (samt Bearer-Falle), Fehlertypen, `_about`-Gesundheit, Identitätsprobe~~ | ✅ **fertig** — 93 Tests offline, 5 live gegen 11.0 (§8.1) |
| **2** | ~~Vokabular-Cache, Label↔URI, Suche mit Facetten, beide Sammlungswege~~ | ✅ **fertig** — 160 offline, 21 live (§8.2) |
| **3** | ~~Knoten, Eigenschaften (beide Wege), Rückleseprobe, Schlagwort-Zusammenführung, Sammlungen, Dateien~~ | ✅ **fertig** — 206 offline, 19 live lesend, 18 live **schreibend** (§8.3) |
| **4** | ~~`edusharing.agent` (§6) plus b-api-Client mit Politik~~ | ✅ **fertig** — 342 offline, 25 live (§8.4) |
| **5** | ~~Abläufe: ein Anwendungsfall, ein Aufruf, ein dict zurück~~ | ✅ **fertig** — siehe FLOWS.de.md und E9 |
| **6** | ~~Die Endpunkte, die der Abgleich mit `wlo-mcp-sc` und der Ideendatenbank als Lücke auswies~~ | ✅ **fertig** — Beziehungen, Serienobjekte, Veröffentlichen, Herkunft, Bewertungen, Kommentare, Gruppen, Vorschläge, Workflow |
| **7** | ~~Kuratierte Seiten (der Page Builder)~~ | ✅ **fertig** — `pages.py`, `flows/pages.py` |
| **8** | ~~Der Textextraktionsdienst neben dem Repositorium~~ | ✅ **fertig** — `extraction.py` |
| **9** | ~~Der Metadata Agent und die durchgereichten OpenAI-Routen der b-api~~ | ✅ **fertig** — `metadata_agent.py`, `bapi/passthrough.py`; gemessen gegen Staging **und** Produktiv |

Die Dokumentation läuft mit, nicht hinterher: **jedes Beispiel unter
`docs/examples/` ist ein ausführbarer Test gegen Staging.** Was dort nicht
läuft, kommt nicht ins README.

### 8.1 Etappe 1 — was dabei herauskam

| Modul | Verantwortung |
|---|---|
| `errors.py` | Fehlertypen; Zuordnung aus Status **und** Java-Klassennamen |
| `urls.py` | Repository-URL normalisieren, Deep Links ablehnen |
| `auth.py` | Zugangsdaten als Werte; Bearer abgelehnt; Passwörter nie im `repr` |
| `transport.py` | httpx, Zeitlimit, Wiederholung, Nebenläufigkeit, Credential-Grenze |
| `_http.py` | Begrenztes Einlesen dekodierter Antworten, gemeinsam für Repository-Downloads und binäre b-api-Aufrufe |
| `_decoding.py` | Schrittweises Dekodieren von gzip/deflate mit begrenzter Ausgabe und begrenzten Zwischenschichten |
| `_checks.py` | Regeln für Eingaben des Aufrufers, die mehr als ein Modul braucht — MIME-Typ, Sprache — an einer Stelle, damit ein zweites Modul sie findet (Audit ARC-23-1) |
| `_json.py` | Der eine Leser für JSON, das eine andere Maschine schrieb: zu tiefe Verschachtelung wird zu dem `ValueError`, den jeder Aufrufer behandelt; ein Wächter schlägt bei jedem Parse anderswo an (Audit COR-23-5) |
| `_sync.py` | Ereignisschleife in einem Hintergrundfaden für die synchrone Fläche |
| `repository.py` | `AsyncRepository` / `Repository`, `about()`, `whoami()`, `raw` |
| `extraction.py` | Der Textextraktionsdienst neben dem Repositorium und die Prüfungen davor |

Vier Entscheidungen, die beim Bauen fielen, jede im Code begründet:

1. **Wiederholungen richten sich nach dem Fehler*typ*, nicht nach dem
   Statuscode.** Sonst würde ein „Not allowed for guest user" dreimal
   wiederholt — dieselbe Anfrage, die nie gelingen kann, gegen ein
   Repositorium, das nichts falsch gemacht hat.
   Und nach der *Methode* (Audit COR-1, 03.09.2026): nach einem Timeout nach
   dem Senden oder einem 5xx wird nur erneut gesendet, was zweimal ankommen
   darf — Lesezugriffe und die Schreibvorgänge, die bloß einen Zustand setzen
   und das sagen (`idempotent=True`). Ein Anlegen oder Löschen im Zweifel
   wirft, statt womöglich zweimal zu laufen; ein Verbindungsfehler von vor dem
   Senden wird für jede Methode wiederholt.
2. **Die synchrone Fläche fährt ihre eigene Schleife in ihrem eigenen Faden**
   statt `asyncio.run()`. Sonst scheitert sie in Jupyter — genau bei dem
   Publikum, für das sie existiert.
3. **Ein zweiter Dienst wird für sich gebaut, nicht ans Repositorium
   gehängt.** Die b-api, der Textextraktionsdienst und der Metadaten-Agent
   stehen alle neben edu-sharing, nicht darin, und eine Verbindung zu einem Repositorium sagt
   nichts darüber, ob es einen von beiden gibt. Deshalb hängt keiner an
   `Repository`: sie haben eine eigene Adresse, eine eigene Umgebungsvariable
   und einen eigenen Client. **Keiner der drei trägt eine
   Vorgabeadresse** — weder die b-api noch der Extraktionsdienst noch der
   Metadaten-Agent. Jeder wirft, wenn seine Variable fehlt; je ein Test in
   `test_bapi_client.py`, `test_extraction.py` und `test_metadata_agent.py`
   hält das fest.

   Bis zum 08.09.2026 stand hier das Gegenteil über die b-api, mitsamt
   Begründung: ein Gateway, das viele Installationen teilen. So war es bis zum
   28.08.2026, dann wurde es als brechende Änderung entfernt — mit einem fest
   eingetragenen Gateway schickte schon das bloße Setzen von `B_API_KEY` den
   Schlüssel an einen Host, den niemand gewählt hatte. Der Extraktionsdienst
   hatte das von Anfang an verweigert, weil der MCP gemessen hatte, was eine
   Vorgabe dort kostet: auf Staging zeigend schickte er Produktions-URLs in
   eine andere Umgebung. Ein Nachweis, der eine Sicherheitsentscheidung
   umdreht, ist schlimmer als keiner — er liest sich wie eine Begründung, sie
   rückgängig zu machen.
4. **Zugangsdaten gehen nur an die konfigurierte Repository-URL**, geprüft mit
   Präfix *und* Grenze. Ein blankes `startswith` ließe
   `https://repo.example.test.attacker.test` durch.

Die drei kritischen Verhaltensweisen sind durch Mutationstests abgedeckt:
Semaphor abschalten, Wiederholung auf den Statuscode umstellen, die
Grenzprüfung durch ein blankes `startswith` ersetzen — jede Mutation färbt
genau ihren eigenen Test rot.

### 8.2 Etappe 2 — was dabei herauskam

| Modul | Verantwortung |
|---|---|
| `vocab.py` | Label↔URI gegen `/values`, gecacht mit einer Sperre je Eigenschaft |
| `search.py` | ngsearch mit Filtern, Facetten, Feld-Aliasen |
| `results.py` | Wertobjekte, gemeinsam für Material- und Sammlungssuche |
| `collections.py` | Beide Sammlungssuchen, nebenläufig, zusammengeführt |

**Zur Allgemeingültigkeit (E4).** Eine zweite *Instanz* ließ sich nicht
hinzuziehen: `stable.demo.edu-sharing.net` (edu-sharing 9.0) erlaubt anonym
**nichts** — selbst `/iam/…/-me-` antwortet mit 401. Das ist als Live-Test
festgehalten (die Bibliothek muss daraus einen `AuthenticationError` machen und
nicht abstürzen).

Geprüft wurde stattdessen gegen **zwei Metadatensätze derselben Instanz**:
`-default-` (Contentbuffet, 88 Widgets, 22 Vokabulare) und `mds_oeh`
(236 Widgets, 107 Vokabulare). Sie liefern für dieselbe Anfrage verschiedene
Ergebnismengen (2825 gegen 17994 für „Physik"), und derselbe
Bibliothekscode arbeitet mit beiden. Das ist schwächer als eine fremde Instanz,
aber es ist eine echte Trennung: trüge die Bibliothek WLO-Annahmen, würde
`-default-` scheitern.

Fünf Befunde haben den Entwurf geprägt — alle gemessen, drei davon berichtigen
vorher angenommenes Wissen:

1. **Ein Vokabular zu führen und filterbar zu sein sind zwei verschiedene
   Dinge.** `ccm:taxonid` hat in beiden Metadatensätzen ein Vokabular, ist aber
   nur in `mds_oeh` filterbar; `ccm:educationaltypicalagerangecluster` in
   keinem. Ein Live-Test ist genau darüber gestolpert. Die Bibliothek ergänzt
   die Servermeldung jetzt um den fehlenden Hinweis.
2. **Die OpenAPI-Spezifikation beschreibt die Vokabularantwort falsch.** Sie
   deklariert `MdsValue {id, caption}`; was ankommt, ist
   `{key, displayString}`. Wer der generierten Schicht vertraut, liest leere
   Felder — die Rechtfertigung für die handgeschriebene Schicht, in einem Satz.
3. **`pattern` ist eine Teilstring-, keine Präfixsuche.** `"ysik"` findet
   Physik, Atomphysik, Kernphysik. Die ursprüngliche Präfixannahme wurde von
   einem Live-Test widerlegt.
4. **Die beiden Sammlungssuchen gehen wirklich auseinander** — für „Deutsch"
   war die Überschneidung **null** (25 gegen 25 verschiedene Sammlungen), für
   „Physik" steuert jede fünf eigene bei. Beide werden gebraucht. (Anmerkung:
   das *Ausmaß* der Überschneidung schwankt zwischen Aufrufen, da jeder Weg 25
   von 876 zurückgibt — siehe §8.5.)
5. **Query-Namen sind nicht introspizierbar.** `ngsearch` taucht in keiner
   API-Antwort auf; die `lists` im Metadatensatz tragen alle `queries: []`. Der
   Name ist Konvention und damit ein Parameter, kein ermittelter Wert.

### 8.3 Etappe 3 — was dabei herauskam

| Modul | Verantwortung |
|---|---|
| `nodes.py` | Knoten lesen/anlegen/ändern/löschen, Rückleseprobe, Schlagwort-Zusammenführung |
| `content.py` | Dateien hoch- und herunterladen, Volltext |
| `info.py` | Wertobjekte für Instanzauskünfte (aus `repository.py` herausgelöst) |
| `collections.py` | zusätzlich: Sammlung anlegen, Referenzen setzen und entfernen |
| `_sync.py` | zusätzlich: `SyncTransport`, `SyncNode`, `SyncNodeContent` |

**Die zentrale Messung**, an einem Wegwerf-Knoten genommen:

| Vorgang | HTTP | gespeichert |
|---|---|---|
| `PUT /metadata`, Eigenschaft im Metadatensatz | 200 | ja |
| `PUT /metadata`, Eigenschaft **nicht** darin | **200** | **nein** |
| `POST /property`, dieselbe Eigenschaft | 200 | ja |
| `PUT /metadata`, erfundenes Feld | **200** | **nein** |

Zweimal ein Erfolgscode für etwas, das nicht geschah. Der Live-Test belegt
beide Seiten: mit Rückleseprobe scheitert der Vorgang, mit `verify=False`
meldet derselbe Aufruf Erfolg und der Wert ist weg.

Vier weitere Befunde, drei davon haben Annahmen widerlegt:

1. **`downloadUrl` ist kein Beleg dafür, dass es Inhalt gibt.** Sie ist immer
   gesetzt, und ein Knoten ohne Datei antwortet mit 200 und null Bytes — ohne
   Beanstandung. Verlässlich ist `content.hash`: `None` ohne Inhalt, gesetzt
   bei einer 0-Byte-Datei. `cclom:size` ist in beiden Fällen `None` und taugt
   deshalb nicht.
2. **Ein `ccm:map` aus der Knoten-API ist keine Sammlung.** Ihm fehlt der
   Aspekt `collection`; jeder Referenzversuch endet in `400 … is not a
   collection`. Sammlungen brauchen den Sammlungsendpunkt — und dort wird
   `-collectionhome-` **nicht** aufgelöst (404), anders als in der Knoten-API.
   Die Sammlungswurzel heißt dort `-root-`.
3. **Nach `addReference` ist die Referenz nicht sofort sichtbar.**
   `/children/references` liefert eine leere Liste, obwohl die Referenz
   existiert — der zweite Versuch antwortet mit 409. Eine Rückleseprobe wäre
   hier also falsch und würde falschen Alarm schlagen; `add()` lässt sie weg
   und meldet über den Rückgabewert, ob etwas neu entstanden ist.
4. **Eine Eigenschaft zu löschen geht mit einem `null`-Körper *und* ganz ohne
   Körper.** Geschickt wird das ausdrückliche `null` — der dokumentierte Weg;
   ein Weglassen ist etwas, das eine andere Version anders lesen könnte.

**Zwei eigene Lücken**, beide beim Benutzen der Bibliothek aufgefallen und
geschlossen: das synchrone `Repository` hatte kein `raw`, und `SyncNode.content`
gab ein Objekt mit asynchronen Methoden zurück, deren Aufrufe ins Leere gingen.
Jede neue asynchrone Fläche braucht ihren synchronen Durchgriff — das ist der
Wartungspreis von Entscheidung E3 und gehört auf die Prüfliste jeder
Erweiterung.

**Schreibtests** laufen nur mit `-m write`, ausschließlich in einem eigens
angelegten Ordner im Home des Testkontos, und räumen ihn danach weg. Der
Bestand wurde nach jedem Lauf gegen seinen Ausgangszustand verglichen.

### 8.4 Etappe 4 — was dabei herauskam

| Modul | Verantwortung |
|---|---|
| `agent/safety.py` | Darf diese URL abgerufen werden? (SSRF) |
| `agent/sanitize.py` | Fremdinhalt für einen Modellkontext |
| `agent/format.py` | Treffer, kompakt, budgetiert, ohne die Belegstelle zu verlieren |
| `agent/result.py` | Fehler als Ergebnisse statt als Ausnahmen |
| `agent/confirm.py` | Zeigen, was geschähe, und es dann tun |
| `bapi/models.py` | Welches Modell: Wahl, Auslastung, Abkündigung — reine Funktionen |
| `bapi/body.py` | Wie der Anfragerumpf aussehen muss — reine Funktionen |
| `bapi/_response.py` | Verschachtelte Antwortprüfung für Proxy- und Template-Parser; explizite Entscheidungen und vollständige Embedding-Indizes |
| `bapi/choice.py` | Welches Modell antwortet: eine Gruppe oder eine ausdrückliche Liste, die Rangfolge, wenn der Aufrufer die Wahl offen ließ, die Obergrenze beim Raten und der Wechsel zum nächsten Kandidaten. `chat` und `respond` teilen sie |
| `bapi/client.py` | HTTP zur b-api, Wiederholung, Nebenläufigkeit, Cache mit Verfallszeit |
| `bapi/passthrough.py` | Durchgereichte Routen — Einbettungen, Moderation, Bilder, `call` für JSON und `call_bytes` für binäre Antworten |

Drei Entscheidungen, die eine Erklärung brauchen:

1. **`sanitize` erkennt keine Angriffsformulierungen.** Eine Musterliste gegen
   „ignoriere alle vorherigen Anweisungen" lässt sich umformulieren — und einen
   Unterrichtstext *über* Prompt Injection würde sie zerstückeln, obwohl er ein
   legitimes Material ist. Übrig bliebe falsche Sicherheit. Stattdessen:
   unsichtbare Steuerzeichen entfernen (Zero-Width, Bidi, Unicode-Tag-Block)
   und den Inhalt so markieren, dass er nicht ausbrechen kann.
2. **`safety` löst keine Namen auf.** `internal-service.example.com` kann auf
   `10.0.0.5` zeigen und trotzdem durchgehen. Hier aufzulösen wäre wegen DNS
   Rebinding ohnehin Sicherheitstheater; wer es ausschließen muss, braucht
   einen ausgehenden Proxy. Die Grenze steht im Docstring statt in einem
   Sicherheitsversprechen.
3. **`format` budgetiert in Zeichen, nicht in Token.** Eine Token-Schätzung
   ohne den Tokenizer des Zielmodells wäre geraten. Und: passt nicht einmal der
   Kopf ins Budget, gewinnt die Belegstelle und das Budget wird überschritten —
   ein Treffer ohne `id` und `url` ist wertlos.

**Zwei Befunde aus den Live-Tests:**

* **`status: ready` heißt nicht, dass ein Modell antwortet.**
  `apertus-70b-instruct-2509` meldet `ready` und `demand: 0` und antwortet mit
  `503 Model pricing unavailable — cannot enforce cost quota`. Das steht in
  keiner Modellliste. Bei **automatischer** Wahl fällt der Client deshalb auf
  das nächste Modell durch (`last_model` sagt, welches es wurde); bei einer
  **ausdrücklich** genannten Modell-ID nicht — das wäre ein stiller Austausch.
* **Rauschen im Modellkontext:** manche Datensätze tragen die Zeichenkette
  `null` als `_DISPLAYNAME`, und der Server liefert „meintest du …?" auch neben
  57 Treffern. Beides wird jetzt gefiltert; welche Vokabularfelder überhaupt in
  den Kontext gehören, entscheidet der Aufrufer über `label_properties`.

**Ein Mutationstest hat zunächst nicht gebissen.** Der ursprüngliche Test für
„`id` und `url` überleben das Budget" blieb grün, obwohl die Zusicherung
abgeschaltet war — das Budget war zu großzügig gewählt. Er ist geschärft
worden, die Mutation färbt ihn jetzt rot. Ein Mutationstest, der nichts fängt,
ist der gefährlichere Fall: er bescheinigt eine Sicherheit, die es nicht gibt.

**Zur vermerkten Aufteilung von `repository.py`:** nicht durchgeführt. Die
Datei hat eine Verantwortung — der Einstieg, in zwei Ausprägungen — und Etappe
4 hat sie kaum berührt, weil `agent` und `bapi` eigene Unterpakete sind. An der
Zeilengrenze zu schneiden, ohne dass eine zweite Verantwortung aufgetaucht
wäre, hätte nur die Dateizahl erhöht.

### 8.5 Sprachwechsel und eine Korrektur am Testentwurf

Nach Etappe 4 wurden Code, Dokumentation und Feldnamen auf Englisch umgestellt
(Entscheidung E7); die Werte bleiben deutsch, da sie die Labels des
Repositoriums sind. Die Fehlermeldungen gingen mit: sie erreichen Endnutzer und
Modellkontexte, und deutsche Meldungen unter englischen Docstrings wären
dieselbe Spaltung, die die Feld-Aliase gerade hinter sich gelassen hatten.

Dabei kam ein **eigener Fehler im Testentwurf** ans Licht. Der Live-Test für
die Sammlungssuche verlangte mehr Treffer, als ein einzelner Weg zurückgibt,
weil die Überschneidung für „Deutsch" als null gemessen worden war. Das ist
nicht stabil: jeder Weg gibt 25 von 876 Sammlungen zurück, und wie stark sich
diese beiden Auswahlen überschneiden, schwankt von Aufruf zu Aufruf — 25 und 29
Treffer wurden für dieselbe Anfrage beobachtet. Der Test prüft jetzt, was die
Bibliothek zusichert (beide Wege abgefragt, Ergebnis über die Knoten-ID
entdoppelt, Gesamtzahl als Untergrenze gekennzeichnet). Die Messung der
Überschneidung bleibt in der Dokumentation, wo sie hingehört.

### 8.6 Etappen 5 bis 8 — was dabei herauskam

| Modul | Verantwortung |
|---|---|
| `flows/find.py`, `flows/describe.py`, `flows/contents.py` | Die zweite Ebene (E9), und das, worin `discover.py` zerlegt wurde: welche Knoten, was dieser Knoten ist, was an ihm hängt |
| `flows/collections.py`, `flows/tree.py` | Welche Sammlungen — und, weil der Baum ein Graph ist und kein Baum, ihn ablaufen mit Deckel und Dublettenmenge |
| `flows/curate.py` | Die schreibenden Abläufe: anlegen, einsortieren, löschen |
| `flows/rerank.py` | E10: mehrere Anfragevarianten auf einmal, ihre Ranglisten zusammengeführt |
| `fields.py`, `ranking.py`, `language.py` | Wiederverwendbare Teile der Schicht 2, am 08.09.2026 aus `flows/` heraus verschoben: Kurzname → Eigenschaft und Vokabularauflösung, die Bewertung, die Wortlisten hinter E10. Sie waren von unten nach oben geholt worden (Audit ARC-1); `tests/test_import_direction.py` wacht jetzt über die Richtung |
| `strings.py` | `cap_text` — eine Zeichenkettenfunktion, unter jeder Schicht, die sie benutzt |
| `dto.py` | Eine Lesart eines rohen Knotensatzes: `first`, `title_of`, `node_id_of`, `bare_id`, `render_url`, `page_total` (Audit MNT-1) |
| `retry.py` | Budget, Backoff mit Jitter und `Retry-After` — eine Regel für den Transport, den Extraktionsdienst und die b-api (Audit ARC-2) |
| `relations.py` | Verknüpfungen zwischen Knoten, die nebeneinander stehen |
| `childobjects.py` | Weitere Dokumente, die zu einem Hauptdokument gehören |
| `permissions.py` | Veröffentlichen und die Rechteliste dahinter |
| `placement.py` | Wo ein Knoten sitzt und wer ihn aufgenommen hat |
| `ratings.py`, `comments.py` | Die zwei Endpunkte mit leerem Antwortkörper |
| `people.py` | Gruppen und Mitgliedschaften |
| `suggestions.py`, `workflow.py` | Vorschläge und redaktionelle Übergabe |
| `pages.py`, `flows/pages.py` | Kuratierte Seiten — lesen und die gerenderte Variante setzen |
| `extraction.py` | Der Textextraktionsdienst neben dem Repositorium |
| `metadata_agent.py` | Welche Felder eine Inhaltsart trägt — die Schemata hinter `ccm:oeh_extendedData` |
| `nodes_write.py` | Die Rümpfe hinter `Node.update`, `set_property` und der Schlagwort-Zusammenführung: Feldkürzel und Rückleseprobe (am 02.09.2026 herausgelöst) |

Die Messungen, auf denen diese Module stehen, sind in §7 — dort wurden sie
festgehalten, als sie gemacht wurden. Drei Entscheidungen verdienen eine eigene
Nennung:

1. **Abläufe sind eine zweite Ebene, kein Ersatz.** Jeder Ablauf lässt sich auf
   der API-Ebene mit mehr Code nachbauen, und das Kapitel jedes Ablaufs in
   FLOWS.de.md zeigt genau diesen Code. Beides sichtbar zu halten ist der
   Punkt: eine Anwendung, die einem Ablauf entwächst, soll sehen können, worin
   sie tritt, statt es neu herauszufinden.
2. **Nicht jede Fläche bekommt einen Ablauf.** Bewertungen, Kommentare, das
   Stellen und das Ablehnen eines Vorschlags, Workflow und Gruppen bleiben
   nur auf der API-Ebene. Das *Annehmen* hat einen: `accept_suggestion`
   schreibt, liest zurück und hakt erst dann ab, das sind drei Endpunkte —
   es folgt dieser Regel also, statt sie zu brechen. Ein Ablauf
   verdient seinen Platz dadurch, dass er mehrere Endpunkte verkettet; diese
   bleiben jeweils bei einer Familie, und sie zu umhüllen fügte einen Namen
   hinzu, ohne einen Schritt zu sparen. Das Ablauf-Kapitel sagt das, weil ein
   Leser sonst in FLOWS.de.md nach einem Bewertungs-Ablauf sucht.
3. **Kein Dienst trägt eine Vorgabeadresse.** Weder die b-api noch der
   Extraktionsdienst noch der Metadaten-Agent — siehe §8.1, Entscheidung 3.

**Ein Umbau.** `flows/discover.py` erreichte 671 Zeilen, das 2,2-fache der
Schwelle und das 2,3-fache des nächstgrößten Moduls in seinem Paket. Es hatte
drei Änderungsgründe, und niemand rät `relations` oder `child_objects` hinter
dem Namen „discover". Aufgeteilt in `find` (welche Knoten), `describe` (was
dieser Knoten ist) und `contents` (was an ihm hängt). Die Schnitte kamen aus
dem AST, mit dem Nachweis, dass die Teile die Vorlage Zeichen für Zeichen
ergeben, und die öffentliche Fläche von `Flows` — ihre damals 20 Methoden mit jeder
Signatur und jedem Vorgabewert — wurde davor und danach verglichen und ist
identisch.

`related` ist der eine, der nicht stillhalten wollte: er beginnt bei einer ID
wie die Abläufe in `describe`, aber was er beantwortet, ist eine Suchfrage,
also wohnt er bei `find`. Unter den dreien ist das der einzige verbliebene
modulübergreifende Aufruf, `find` → `describe`, in eine Richtung — über
`flows/` insgesamt gibt es mehr, nachgemessen in §8.8. Der Modul-Docstring sagt das,
statt eine Grenze zu behaupten, die nicht hält.

**Eine Testlücke aus derselben Familie wie die zwei in §8.3.** `SyncRelations`
wurde gebaut und nie geprüft: gemessen waren alle vier Methoden unbelegt. Das
ist der dritte Fall des Wartungspreises von Entscheidung E3 und der Grund,
warum `test_sync_surface.py` überhaupt existiert. `_sync.py` ist jetzt
vollständig abgedeckt.

### 8.7 Der Audit vom 28.08.2026

Ein vollständiger Audit über zwölf Dimensionen fand sechzehn Befunde, fünf
davon gemessen statt vermutet. Alle sind behoben; der Bericht mit den
Belegen steht in [`audits/2026-08-28-audit.md`](audits/2026-08-28-audit.md).

Drei davon hatten dieselbe Ursache und sind der Grund für diesen
Abschnitt: **`agent/` reinigte fremden Text, aber nicht seine Struktur.**
Ein Datensatztitel mit Zeilenumbrüchen fälschte einen vollständigen
Suchtreffer mit fremder `id` und `url`, und zwar vor dem echten; das
`label` von `as_untrusted` konnte den Fremdinhalts-Block schließen, gegen
den der Rumpf ausdrücklich geschützt war; und die SSRF-Prüfung, mit der
das Paket warb, hatte in der Bibliothek keinen Aufrufer, während
`extraction` eine zweite, anders antwortende Kopie trug. Dieses Teilpaket
war das jüngste und das einzige, das nie gegen feindliche Eingaben
gelaufen war — jedes andere hatte eine echte Instanz hinter sich.

Die Reparatur benannte die Regel, statt die Stellen zu flicken:
``sanitize_text`` behält Struktur, und **jeder Verbraucher, dessen
Ausgabeformat diese Struktur benutzt, muss sie abflachen** (``one_line``,
jetzt exportiert). Die URL-Entscheidung ist nach ``urls.py`` gewandert,
damit beide Aufrufer sie teilen.

### 8.8 Etappe 10 — Skills, Volltext und die Ablauf-Helfer

Zehn Module fehlten bis zum 08.09.2026 in jeder Tabelle darüber (Audit
DOC-3). Das Skill-Teilsystem ist das größte davon: vier Module, und das Wort
„Skills" kam in diesem Dokument kein einziges Mal vor.
`tests/test_docs_inventories.py` schlägt jetzt an, wenn ein Modul hier
nirgends genannt ist.

| Modul | Verantwortung |
|---|---|
| `skills.py` | Skills — Datensätze, deren Inhaltsart „Anleitung" sagt und deren angehängte Datei die `SKILL.md` ist. Lesen, die Dateien daneben auflisten, und die Gründe, aus denen ein anonymer Leser eine leere Antwort bekommt (`files_reason`, `content_reason`) |
| `skills_markdown.py` | Was ein Skill-Dokument über sich selbst sagt, gelesen ohne jede Ein- und Ausgabe: Kopfdaten, die `::: ki-skill`-Blöcke, die Überschriften, die sie gruppieren |
| `_markdown_outline.py` | Indizierte Zuordnung von Überschriften und Abschnittsgrenzen für begrenzten Kontextaufbau |
| `skills_registry.py` | Das Register einer Sammlung — welche Skills sie freigegeben hat, nach Arbeitszusammenhängen gruppiert |
| `flows/skills.py` | Derselbe Zugang als schlichte Wörterbücher: `find_skills`, `skill`, `skill_registry`, `pick_skill` |
| `flows/text.py` | `text` — der Volltext eines Materials und, wenn es keinen gibt, welcher der gemessenen Gründe zutrifft |
| `flows/suggest.py` | `accept_suggestion` — einen Vorschlag anwenden, zurücklesen, und erst dann abhaken (Audit COR-3) |
| `flows/serialize.py` | Wertobjekte in schlichte JSON-Strukturen. Das Blatt, das sich vier Ablaufmodule teilen |
| `flows/dedupe.py` | Treffer zusammenfassen, die dasselbe Material mehrfach zeigen |
| `flows/duplicates.py` | Gibt es zu dieser Adresse schon einen Datensatz? |
| `flows/expand.py` | Aus einer Anfrage die wenigen Varianten machen, die zu stellen sich lohnt (E10) |

**Wo die Ablaufmodule einander rufen.** §8.6 sagt, die Teilung von
`flows/discover.py` habe einen modulübergreifenden Aufruf übriggelassen. Das
stimmt *innerhalb der drei*, die dabei entstanden — `find` → `describe` — und
wurde hier als Aussage über `flows/` insgesamt gelesen, die es nicht ist.
Gemessen am 08.09.2026 greifen sieben der fünfzehn Module auf ein
Geschwistermodul zu: `collections` auf fünf (`find`, `pages`, `rerank`,
`serialize`, `tree`), und `serialize` ist das Blatt, das sich vier von ihnen
teilen. `tests/test_import_direction.py` wacht über die Richtung zwischen den
*Schichten*; innerhalb dieses Pakets gibt es keine solche Regel, und es wird
auch keine behauptet.

### 8.9 Etappe 11 — der Template-Modus der b-api

Hinzugekommen am 11.09.2026, siehe E11. Geteilt wie der Proxy: die Form einer
Anfrage in einem Modul, das Senden in einem anderen.

| Modul | Verantwortung |
|---|---|
| `bapi/template_body.py` | Wie eine Template-Anfrage aussehen muss — Konfigurationsverweise, Werte als Listen, die Paare des limited-Modus und die Liste, mit der die schreibenden Routen antworten. Reine Funktionen |
| `bapi/templates.py` | `BapiTemplates`: HTTP an `/api/v1/edu-sharing/*`, eigene Wiederholungsmengen und Fehler aus dem `message` der Antwort — nie aus dem 18-kB-Stacktrace daneben |

## 9. Offene Punkte

1. **Zweite Testinstanz** — teilweise geschlossen. Lesend gegen die
   Produktivinstanz (`redaktion.openeduhub.net`) am 29.08.2026 geprüft, und das
   ergab zwei Befunde, die eine einzelne Instanz nie gezeigt hätte: eine
   Instanz, die ihre Fehlerdetails zurückhält, lässt ein verkapptes 401 wie
   einen Serverfehler aussehen (jetzt **einmal** wiederholt statt
   `max_retries`-mal — 4 Anfragen, wo die Staging 1 braucht), und die lesenden
   Beispiele laufen gegen ein anderes Repositorium, indem allein
   `EDU_SHARING_URL` gesetzt wird.

   Offen bleibt: **schreibend** gegen eine zweite Instanz, und eine Instanz
   unter fremdem Betrieb. `stable.demo.edu-sharing.net` (edu-sharing 9.0) ist
   erreichbar, erlaubt anonym aber **nichts** über `/_about` und
   `/config/v1/values` hinaus; ohne Zugangsdaten taugt sie nicht zur Prüfung.
   Auf der Produktivinstanz wird hier aus Entscheidung nur gelesen, nicht aus
   Beschränkung.
2. **Die Docstrings der Tests sind weiterhin deutsch.** Sie sind das
   Messprotokoll dieses Projekts, werden nicht ausgeliefert und haben kein
   außenstehendes Publikum; sie zu übersetzen wäre eine Gelegenheit, einen
   gemessenen Befund zu verwischen. Eine bewusste Ausnahme von E7.
3. **`nodes.py` wurde am 02.09.2026 geteilt.** Bis Etappe 9 blieb es über
   der Größenschwelle, mit der Begründung, dass jede neue Fläche am Knoten ein
   Durchgriff auf ein eigenes Modul ist. Die Referenz-Umleitung vom 02.09.2026
   hat das geändert: die Schreibdisziplin -- Feldkürzel, Rückleseprobe,
   Schlagwort-Zusammenführung, das Durchschreiben ans Original -- war zu einem
   eigenen Änderungsgrund geworden. Ihre Rümpfe sind nach
   `nodes_write.py` gewandert; `Node` behält die Methoden als einzeilige
   Durchgriffe, die öffentliche Oberfläche hat sich also nicht bewegt. Am Tag
   der Teilung gemessen: 537 Zeilen blieben in `nodes.py` -- das Lesemodell
   und seine Türen -- gegen 200 in `nodes_write.py`. Die Zahlen tragen ihr
   Datum, weil sie der Beleg für die Teilung waren und keine Beschreibung der
   Dateien, wie sie heute dastehen.
   `flows/discover.py` hatte früher eine zweite Verantwortung bekommen und
   wurde auf dieselbe Art geteilt (§8.6).


## Metadatenprofile und zusammengesetzte Abläufe — 0.3.0

| Modul | Verantwortung |
|---|---|
| `profile.py` | Unveränderliche Lese-/Schreib-/Suchkonventionen je Verbindung; benannte WLO-Vorgabe, explizite neutrale Profile |
| `metadata.py` | Echte MDS-Definition je Locale puffern; unabhängige Rückgaben und explizite Invalidierung |
| `vocab_values.py` | Unveränderlicher Vokabulareintrag, über die bestehende Vokabular-API exportiert |
| `vocab_snapshots.py` | JSON-Format und Prüfung von Kontext und Alter; keine Datei- oder Hintergrundzugriffe |
| `flows/place.py` | Original/Referenz-Identität und schrittweise Platzierung, Veröffentlichung, Entfernung mit Teilergebnissen |
| `flows/context.py` | Eine Inhaltsseite für Kontext/Statistik wiederverwenden; optional konfigurierte Registry |
| `flows/prepare.py` | Rein lesende Entwurfsnormalisierung, Dubletten-/Pflichtfeld-Vorprüfung und optionale Extraktion |

Ein MDS beschreibt Widgets; daraus folgen weder Filterbarkeit noch semantische
Schreibrollen. Profile bleiben deshalb explizit. `SearchHit` speichert eine
serialisierbare Kopie der Lesefelder statt des unveränderlichen Profilobjekts:
`dataclasses.asdict`, `replace` und `deepcopy` funktionieren weiter. Synchrone
Adapter führen Snapshot/Restore auf dem Repository-Loop aus. Keine neuen
Laufzeitabhängigkeiten.

Prüfung: HTTP-Grenztests mit eigenen Feldern, URNs/Codes, gleichen Labels,
Cache-Veränderung, Snapshot-Kontext/Alter, bereits öffentlichen Materialien,
fehlgeschlagenen Platzierungsschritten, unvollständigen Dublettenprüfungen und
synchronem Zugriff. Die Live-Abnahme weiterer Installationen steht aus.
[Entwurf und Befundabschluss](plans/2026-09-14-generic-metadata.md).
